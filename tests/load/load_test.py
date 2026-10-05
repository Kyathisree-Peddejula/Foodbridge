"""
Self-contained load / stress test for the FoodBridge API (no extra tools needed besides httpx).

Simulates the real traffic mix of business, NGO and admin users (dashboards, inventory lists,
live donation feed with polling, scans, notifications) and ramps concurrency in stages until
errors or latency blow up.

    python tests/load/load_test.py --base http://localhost:8000/api --stages 10,25,50,100 --seconds 20

Prints per-stage throughput, latency percentiles and error rate, plus the slowest endpoints,
and writes results to tests/load/results.json.
"""
import argparse
import asyncio
import json
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

import httpx

ACCOUNTS = {
    "business": [("hotel@foodbridge.dev", "Demo@12345"), ("bakery@foodbridge.dev", "Demo@12345"),
                 ("store4@foodbridge.dev", "Demo@12345"), ("canteen@foodbridge.dev", "Demo@12345")],
    "ngo": [("hope@foodbridge.dev", "Demo@12345"), ("annapoorna@foodbridge.dev", "Demo@12345"),
            ("greenhands@foodbridge.dev", "Demo@12345")],
    "admin": [("admin@foodbridge.dev", "Admin@12345")],
}
ROLE_MIX = [("business", 0.6), ("ngo", 0.35), ("admin", 0.05)]
# (weight, method, path) - mirrors what the Flutter screens call
TASKS = {
    "business": [(20, "GET", "/analytics/business/"), (15, "GET", "/inventory/batches/?in_stock=true&page_size=50"),
                 (8, "GET", "/marketplace/listings/?page_size=50"), (8, "GET", "/marketplace/listings/suggestions/"),
                 (6, "GET", "/predictions/risk/summary/"), (6, "GET", "/expiry/alerts/?is_acknowledged=false"),
                 (6, "GET", "/pickups/calendar/"), (6, "GET", "/notifications/unread-count/"),
                 (4, "GET", "/inventory/products/?page_size=100"), (4, "GET", "/analytics/impact/?scope=mine"),
                 (3, "GET", "/predictions/reorder/"), (3, "POST", "/inventory/scan/")],
    "ngo": [(30, "GET", "/marketplace/listings/feed/"), (20, "GET", "/analytics/ngo/"), (15, "GET", "/pickups/?page_size=50"),
            (10, "GET", "/pickups/calendar/"), (10, "GET", "/notifications/unread-count/"),
            (5, "GET", "/marketplace/requirements/"), (5, "GET", "/analytics/impact/?scope=platform")],
    "admin": [(50, "GET", "/analytics/admin/"), (30, "GET", "/analytics/impact/?scope=platform"),
              (20, "GET", "/organizations/ngo-network/")],
}


def pct(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    k = min(len(s) - 1, max(0, int(round(p / 100 * (len(s) - 1)))))
    return s[k]


async def login(client, base):
    tokens = {}
    for role, accs in ACCOUNTS.items():
        tokens[role] = []
        for email, pw in accs:
            r = await client.post(f"{base}/auth/login/", json={"email": email, "password": pw})
            if r.status_code == 200:
                tokens[role].append(r.json()["access"])
    missing = [r for r, t in tokens.items() if not t]
    if missing:
        raise SystemExit(f"Login failed for roles {missing} - is the demo data seeded?")
    return tokens


async def user_loop(client, base, tokens, stop_at, stats, think):
    role = random.choices([r for r, _ in ROLE_MIX], weights=[w for _, w in ROLE_MIX])[0]
    headers = {"Authorization": f"Bearer {random.choice(tokens[role])}"}
    tasks = TASKS[role]
    weights = [t[0] for t in tasks]
    while time.perf_counter() < stop_at:
        _, method, path = random.choices(tasks, weights=weights)[0]
        t0 = time.perf_counter()
        try:
            if method == "POST":   # barcode scan receiving 1 unit of a load-test product
                r = await client.post(f"{base}{path}", headers=headers, json={
                    "barcode": f"LOAD-{random.randint(1, 20)}", "action": "receive", "quantity": 1,
                    "name": "Load test bread"})
            else:
                r = await client.get(f"{base}{path}", headers=headers)
            ok = r.status_code < 400
            code = r.status_code
        except httpx.HTTPError as exc:
            ok, code = False, type(exc).__name__
        ms = (time.perf_counter() - t0) * 1000
        key = path.split("?")[0]
        stats["lat"].append(ms)
        stats["by_ep"][key].append(ms)
        if not ok:
            stats["errors"][str(code)] += 1
        if think:
            await asyncio.sleep(random.uniform(0, think))


async def stage(base, tokens, users, seconds, think):
    stats = {"lat": [], "by_ep": defaultdict(list), "errors": defaultdict(int)}
    limits = httpx.Limits(max_connections=users + 10, max_keepalive_connections=users + 10)
    async with httpx.AsyncClient(timeout=30, limits=limits) as client:
        t0 = time.perf_counter()
        stop_at = t0 + seconds
        await asyncio.gather(*(user_loop(client, base, tokens, stop_at, stats, think) for _ in range(users)))
        wall = time.perf_counter() - t0
    n = len(stats["lat"])
    errs = sum(stats["errors"].values())
    return {
        "users": users, "requests": n, "rps": round(n / wall, 1), "error_rate": round(100 * errs / max(n, 1), 2),
        "errors": dict(stats["errors"]), "p50_ms": round(pct(stats["lat"], 50), 1),
        "p95_ms": round(pct(stats["lat"], 95), 1), "p99_ms": round(pct(stats["lat"], 99), 1),
        "mean_ms": round(statistics.fmean(stats["lat"]), 1) if n else 0,
        "slowest": sorted(({"endpoint": k, "p95_ms": round(pct(v, 95), 1), "n": len(v)}
                           for k, v in stats["by_ep"].items()), key=lambda x: -x["p95_ms"])[:5],
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000/api")
    ap.add_argument("--stages", default="10,25,50,100", help="concurrent virtual users per stage")
    ap.add_argument("--seconds", type=int, default=20)
    ap.add_argument("--think", type=float, default=0.0, help="max think time between requests (s); 0 = stress")
    ap.add_argument("--out", default=str(Path(__file__).with_name("results.json")))
    a = ap.parse_args()
    async with httpx.AsyncClient(timeout=30) as c:
        tokens = await login(c, a.base)
    results = []
    print(f"{'users':>5} {'req':>6} {'rps':>7} {'p50':>7} {'p95':>7} {'p99':>7} {'err%':>6}")
    for users in [int(x) for x in a.stages.split(",")]:
        r = await stage(a.base, tokens, users, a.seconds, a.think)
        results.append(r)
        print(f"{r['users']:>5} {r['requests']:>6} {r['rps']:>7} {r['p50_ms']:>7} {r['p95_ms']:>7} {r['p99_ms']:>7} "
              f"{r['error_rate']:>6}  {r['errors'] or ''}")
    print("\nSlowest endpoints at peak stage (p95 ms):")
    for s in results[-1]["slowest"]:
        print(f"  {s['endpoint']:45} {s['p95_ms']:>8}  (n={s['n']})")
    Path(a.out).write_text(json.dumps(results, indent=2))
    print(f"\nSaved {a.out}")


if __name__ == "__main__":
    asyncio.run(main())
