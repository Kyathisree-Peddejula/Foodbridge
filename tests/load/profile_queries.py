"""
Per-endpoint SQL query count + server time, for every role, against a copy of the demo DB.
Finds N+1 queries before they show up under load.

    SQLITE_PATH=/tmp/profile.sqlite3 python tests/load/profile_queries.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("ML_SERVICE_URL", "http://127.0.0.1:9")   # measure Django only
os.environ.setdefault("ML_SERVICE_TIMEOUT", "0.2")

import django  # noqa: E402

django.setup()
from django.db import connection  # noqa: E402
from django.test.utils import CaptureQueriesContext  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from accounts.models import User  # noqa: E402

ENDPOINTS = {
    "business": ["/api/analytics/business/", "/api/inventory/batches/?page_size=100", "/api/inventory/products/?page_size=100",
                 "/api/inventory/transactions/?page_size=100", "/api/expiry/alerts/?page_size=100",
                 "/api/marketplace/listings/?page_size=100", "/api/marketplace/listings/suggestions/",
                 "/api/predictions/risk/summary/", "/api/predictions/reorder/", "/api/pickups/?page_size=100",
                 "/api/pickups/calendar/", "/api/analytics/impact/?scope=mine", "/api/notifications/?page_size=100",
                 "/api/organizations/ngo-network/"],
    "ngo": ["/api/analytics/ngo/", "/api/marketplace/listings/feed/", "/api/marketplace/requirements/",
            "/api/pickups/?page_size=100"],
    "admin": ["/api/analytics/admin/", "/api/analytics/impact/?scope=platform"],
}
USERS = {"business": "hotel@foodbridge.dev", "ngo": "hope@foodbridge.dev", "admin": "admin@foodbridge.dev"}


def main():
    rows = []
    for role, urls in ENDPOINTS.items():
        c = APIClient()
        c.force_authenticate(User.objects.get(email=USERS[role]))
        for url in urls:
            c.get(url)                                   # warm caches
            with CaptureQueriesContext(connection) as q:
                t = time.perf_counter()
                r = c.get(url)
                ms = (time.perf_counter() - t) * 1000
            rows.append((role, url, r.status_code, len(q), ms))
    print(f"{'role':9} {'endpoint':52} {'status':6} {'queries':7} {'ms':>7}")
    for role, url, st, n, ms in rows:
        flag = "  <-- N+1?" if n > 25 else ""
        print(f"{role:9} {url:52} {st:<6} {n:<7} {ms:7.1f}{flag}")
    return rows


if __name__ == "__main__":
    main()
