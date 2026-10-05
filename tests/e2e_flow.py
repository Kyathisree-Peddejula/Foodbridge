"""End-to-end smoke test across all modules (run with Django on :8000 and ML service on :8001).

inventory input (manual, CSV, POS, scan) -> expiry alerts -> waste prediction -> listing -> AI match
-> NGO claim -> both confirm -> collect -> complete -> dashboards & impact.
"""
import io
import os
import sys
from datetime import date, datetime, timedelta

import requests

API = os.environ.get("API", "http://localhost:8000/api")
OK = []


def check(name, cond, extra=""):
    OK.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))


def login(email, pw="Demo@12345"):
    r = requests.post(f"{API}/auth/login/", json={"email": email, "password": pw})
    r.raise_for_status()
    s = requests.Session()
    s.headers["Authorization"] = "Bearer " + r.json()["access"]
    return s, r.json()["user"]


biz, bu = login("hotel@foodbridge.dev")
ngo, nu = login("hope@foodbridge.dev")
check("login business + ngo", bu["role"] == "business" and nu["role"] == "ngo")

# ---- manual entry with auto-classification
code = "89" + datetime.now().strftime("%H%M%S%f")[:10]
p = biz.post(f"{API}/inventory/products/", json={"name": "Paneer tikka tray", "unit": "kg", "barcode": code,
                                                   "unit_weight_kg": 1}).json()
check("manual product + taxonomy classify", p.get("category_detail"), p.get("category_detail", {}).get("slug"))
b = biz.post(f"{API}/inventory/batches/", json={"product": p["id"], "quantity": 30,
                                                  "expiry_date": (date.today() + timedelta(days=1)).isoformat()}).json()
check("receive batch", b.get("id"), f"status={b.get('status')}")

# ---- CSV bulk upload
tmpl = biz.get(f"{API}/inventory/csv-template/?mode=inventory")
check("csv template", tmpl.status_code == 200)
csv = ("name,category,quantity,unit,expiry_date,barcode\n"
       f"Whole wheat bread,bakery,20,pcs,{(date.today()+timedelta(days=2)).isoformat()},\n"
       f"Tomatoes,,15,kg,{(date.today()+timedelta(days=4)).isoformat()},\n")
r = biz.post(f"{API}/inventory/upload-csv/", files={"file": ("inv.csv", io.BytesIO(csv.encode()), "text/csv")},
             data={"mode": "inventory"})
check("csv upload", r.status_code in (200, 201) and r.json().get("rows_created", 0) >= 2, r.text[:120])

# ---- barcode scan
r = biz.post(f"{API}/inventory/scan/", json={"barcode": code, "action": "sell", "quantity": 2})
check("barcode scan sell", r.status_code in (200, 201), r.text[:120])

# ---- POS integration
pos = biz.post(f"{API}/pos/integrations/", json={"name": "Counter POS", "provider": "generic"}).json()
r = requests.post(f"{API}/pos/v1/sales/", headers={"X-POS-Key": pos["api_key"]},
                  json={"transactions": [{"barcode": code, "quantity": 1, "unit_price": "250",
                                          "reference": "R-" + code}]})
check("POS sales push", r.status_code in (200, 201), r.text[:120])

# ---- expiry alerts
r = biz.post(f"{API}/expiry/alerts/scan/")
alerts = biz.get(f"{API}/expiry/alerts/").json()
check("expiry scan + alerts", r.status_code == 200 and alerts.get("count", 0) > 0, f"count={alerts.get('count')}")

# ---- waste prediction (ML service)
run = biz.post(f"{API}/predictions/risk/refresh/", json={}).json()
check("risk refresh", run.get("status") == "done", f"engine={run.get('engine')} scored={run.get('items_scored')}")
fc = biz.get(f"{API}/predictions/forecast/{p['id']}/?horizon=14").json()
check("forecast", len(fc.get("daily", [])) == 14, fc.get("model"))
rec = biz.post(f"{API}/predictions/reorder/", json={})
check("reorder recommendations", rec.status_code == 201 and len(rec.json()) > 0)

# ---- listing with availability windows -> AI matching
now = datetime.now().astimezone()
w = [{"start": (now + timedelta(hours=2)).isoformat(), "end": (now + timedelta(hours=5)).isoformat()}]
lst = biz.post(f"{API}/marketplace/listings/", json={
    "title": "Veg biryani (40 portions)", "description": "Freshly cooked veg biryani", "quantity_kg": 16,
    "expiry_date": (date.today() + timedelta(days=1)).isoformat(), "dietary_tags": ["veg"], "windows": w}).json()
check("create listing", lst.get("id"), lst.get("category_detail", {}).get("name") if lst.get("category_detail") else lst)
m = biz.get(f"{API}/marketplace/listings/{lst['id']}/matches/").json()
check("AI matches", len(m) > 0, f"top={m[0]['ngo']['name']} {m[0]['score']}" if m else "")
sugg = biz.get(f"{API}/marketplace/listings/suggestions/")
check("surplus suggestions from risk", sugg.status_code == 200)

# ---- NGO feed & claim
feed = ngo.get(f"{API}/marketplace/listings/feed/").json()
check("NGO live feed ranked", isinstance(feed, list), f"{len(feed)} listings")
win_id = lst["windows"][0]["id"]
pk = ngo.post(f"{API}/marketplace/listings/{lst['id']}/claim/", json={"quantity_kg": 10, "window": win_id})
check("NGO claim", pk.status_code == 201, pk.text[:150])
pk = pk.json()
r1 = biz.post(f"{API}/pickups/{pk['id']}/confirm/")
r1 = r1.json()
r2 = ngo.post(f"{API}/pickups/{pk['id']}/confirm/").json()
check("both confirm -> confirmed", r2.get("status") == "confirmed" or r1.get("status") == "confirmed", r2.get("status"))
cal = ngo.get(f"{API}/pickups/calendar/", params={"start": date.today().isoformat(),
                                                   "end": (date.today() + timedelta(days=7)).isoformat()})
check("pickup calendar", cal.status_code == 200)
r = ngo.post(f"{API}/pickups/{pk['id']}/collect/", json={"driver_name": "Ravi"})
check("collect (in transit)", r.json().get("status") == "in_transit", r.text[:120])
r = ngo.post(f"{API}/pickups/{pk['id']}/complete/", json={"quantity_received_kg": 10, "beneficiaries_served": 30})
check("complete delivery", r.json().get("status") == "completed", r.text[:120])

n = biz.get(f"{API}/notifications/unread-count/").json()
check("notifications", n, n)

# ---- dashboards
for who, s, path in [("business", biz, "analytics/business/"), ("ngo", ngo, "analytics/ngo/"),
                     ("impact", biz, "analytics/impact/?scope=platform")]:
    r = s.get(f"{API}/{path}")
    check(f"{who} dashboard", r.status_code == 200, ",".join(list(r.json())[:6]))
adm, _ = login("admin@foodbridge.dev", "Admin@12345")
r = adm.get(f"{API}/analytics/admin/")
check("admin overview", r.status_code == 200, ",".join(r.json().keys()))

print(f"\n{sum(OK)}/{len(OK)} checks passed")
sys.exit(0 if all(OK) else 1)
