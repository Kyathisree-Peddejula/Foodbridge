"""
Weeks 7-8 · end-to-end integration across all modules, in one process:

    inventory input (CSV + POS + scan)  →  waste predictor (real FastAPI + Prophet/LSTM)
      →  redistribution matcher  →  pickup scheduling  →  business / NGO / impact / admin dashboards
"""
from datetime import timedelta

from inventory.models import InventoryBatch, POSIntegration
from marketplace.models import NGORequirement

from .base import TODAY, FBTestCase, iso, later, live_ml_service


class FullPipelineTests(FBTestCase):
    def test_inventory_to_dashboard(self):
        biz, ngo = self.api(self.u_biz), self.api(self.u_ngo)
        req = NGORequirement.objects.create(ngo=self.ngo, title="Hot meals for shelter", max_distance_km=10)
        req.categories.add(self.cat["cooked-meals"])

        # 1. inventory input - CSV history + stock, POS sale, barcode scan
        hist = "sku,name,type,quantity,occurred_at\n" + "".join(
            f"BIR,Veg biryani,sale,{6 + d % 3},{TODAY() - timedelta(days=d)}\n" for d in range(1, 29))
        r = biz.post("/api/inventory/upload-csv/", {"file": self.csv(hist), "mode": "transactions"}, format="multipart")
        self.assertEqual(r.json()["rows_failed"], 0, r.json())
        stock = f"sku,name,quantity,unit,expiry_date,unit_weight_kg\nBIR,Veg biryani,120,portion,{TODAY() + timedelta(days=1)},0.35\n"
        self.assertEqual(biz.post("/api/inventory/upload-csv/", {"file": self.csv(stock), "mode": "inventory"},
                                  format="multipart").json()["rows_created"], 1)
        key = POSIntegration.objects.create(organization=self.biz, name="Till").api_key
        self.api().post("/api/pos/v1/sales/", {"transactions": [{"sku": "BIR", "quantity": 10, "reference": "B1"}]},
                        format="json", HTTP_X_POS_KEY=key)
        biz.post("/api/inventory/scan/", {"barcode": "8900001", "action": "receive", "quantity": 4,
                                          "name": "Masala chai 1L"}, format="json")
        batch = InventoryBatch.objects.get(product__sku="BIR")
        self.assertEqual(batch.quantity, 110)
        self.assertEqual(batch.status, "expiring")                      # expiry engine ran after CSV import

        # 2. waste predictor - real ML service scores the batch
        with live_ml_service():
            run = biz.post("/api/predictions/risk/refresh/", {}, format="json").json()
        self.assertEqual(run["engine"], "ml-service")
        batch.refresh_from_db()
        self.assertIn(batch.risk_level, ("high", "critical"))
        self.assertGreater(batch.expected_waste_qty, 50)                # ~8/day demand vs 110 portions, 1 day left
        sugg = biz.get("/api/marketplace/listings/suggestions/").json()
        self.assertEqual(sugg[0]["id"], batch.id)

        # 3. redistribution matcher - list the predicted surplus, NGO sees it ranked first
        l = biz.post("/api/marketplace/listings/from-batch/", {"batch": batch.id}, format="json").json()
        self.assertAlmostEqual(l["quantity_units"], batch.expected_waste_qty, places=3)
        self.assertAlmostEqual(l["quantity_kg"], round(batch.expected_waste_qty * 0.35, 3), places=2)
        matches = biz.get(f"/api/marketplace/listings/{l['id']}/matches/").json()
        self.assertEqual(matches[0]["ngo"]["id"], self.ngo.id)
        self.assertEqual(ngo.get("/api/marketplace/listings/feed/").json()[0]["id"], l["id"])

        # 4. pickup scheduling - claim, both confirm, collect, deliver
        kg = l["quantity_kg"]
        p = ngo.post(f"/api/marketplace/listings/{l['id']}/claim/",
                     {"quantity_kg": kg, "scheduled_start": iso(later(1)), "scheduled_end": iso(later(3))},
                     format="json").json()
        biz.post(f"/api/pickups/{p['id']}/confirm/")
        ngo.post(f"/api/pickups/{p['id']}/collect/")
        ngo.post(f"/api/pickups/{p['id']}/complete/", {"beneficiaries_served": 40}, format="json")
        batch.refresh_from_db()
        self.assertAlmostEqual(batch.quantity, 110 - l["quantity_units"], places=2)

        # 5. dashboards agree with each other
        bd = biz.get("/api/analytics/business/").json()
        nd = ngo.get("/api/analytics/ngo/").json()
        imp = biz.get("/api/analytics/impact/?scope=mine").json()
        adm = self.api(self.admin).get("/api/analytics/admin/").json()
        self.assertAlmostEqual(bd["kpis"]["donated_this_month_kg"], kg, places=1)
        self.assertAlmostEqual(nd["kpis"]["food_received_kg"], kg, places=1)
        self.assertEqual(nd["kpis"]["beneficiaries_reached"], 40)
        self.assertAlmostEqual(imp["food_diverted_kg"], kg, places=1)
        self.assertEqual(adm["recent_operations"][0]["status"], "completed")
        self.assertEqual(bd["donation_tracker"]["pickups"]["completed"], 1)
        kinds = set(self.biz.notifications.values_list("kind", flat=True))
        self.assertTrue({"expiry", "pickup"} <= kinds)


class EmptyStateTests(FBTestCase):
    """Dashboards must work for brand-new organizations with no data."""

    def test_new_org_dashboards(self):
        for user, url in [(self.u_biz, "/api/analytics/business/"), (self.u_ngo, "/api/analytics/ngo/"),
                          (self.u_biz, "/api/analytics/impact/?scope=mine"), (self.admin, "/api/analytics/admin/"),
                          (self.u_biz, "/api/predictions/risk/summary/"), (self.u_biz, "/api/marketplace/listings/suggestions/"),
                          (self.u_ngo, "/api/marketplace/listings/feed/"), (self.u_biz, "/api/pickups/calendar/")]:
            r = self.api(user).get(url)
            self.assertEqual(r.status_code, 200, (url, r.content[:200]))

    def test_org_without_coordinates_still_matches(self):
        self.biz.latitude = self.biz.longitude = None
        self.biz.save()
        l = self.api(self.u_biz).post("/api/marketplace/listings/", {"title": "Bread", "quantity_kg": 3,
                                      "expiry_date": str(TODAY())}, format="json")
        self.assertEqual(l.status_code, 201, l.content)
        m = self.api(self.u_biz).get(f"/api/marketplace/listings/{l.json()['id']}/matches/").json()
        self.assertTrue(m)
        self.assertIsNone(m[0]["distance_km"])


class CacheInvalidationTests(FBTestCase):
    """Dashboards are cached, but every write must be visible immediately."""

    def test_dashboard_reflects_writes(self):
        c = self.api(self.u_biz)
        before = c.get("/api/analytics/business/").json()["kpis"]["active_batches"]
        self.stock(qty=5, days=3)
        self.assertEqual(c.get("/api/analytics/business/").json()["kpis"]["active_batches"], before + 1)

    def test_platform_impact_reflects_other_orgs(self):
        admin = self.api(self.admin)
        self.assertEqual(admin.get("/api/analytics/impact/?scope=platform").json()["pickups_completed"], 0)
        l = self.api(self.u_biz).post("/api/marketplace/listings/", {"title": "Bread", "quantity_kg": 3,
                                      "expiry_date": str(TODAY())}, format="json").json()
        p = self.api(self.u_ngo).post(f"/api/marketplace/listings/{l['id']}/claim/",
                                      {"quantity_kg": 3, "window": l["windows"][0]["id"]}, format="json").json()
        self.api(self.u_biz).post(f"/api/pickups/{p['id']}/confirm/")
        self.api(self.u_ngo).post(f"/api/pickups/{p['id']}/complete/", {}, format="json")
        self.assertEqual(admin.get("/api/analytics/impact/?scope=platform").json()["pickups_completed"], 1)

    def test_bad_feed_params_are_400(self):
        self.assertEqual(self.api(self.u_ngo).get("/api/marketplace/listings/feed/?min_score=high").status_code, 400)
