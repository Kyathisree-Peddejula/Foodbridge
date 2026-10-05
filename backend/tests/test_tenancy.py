"""Multi-tenant isolation and role permissions."""
from .base import FBTestCase


class TenancyTests(FBTestCase):
    def test_business_cannot_see_or_touch_another_tenants_stock(self):
        theirs = self.stock(org=self.biz2, name="Their curd")
        c = self.api(self.u_biz)
        ids = [b["id"] for b in c.get("/api/inventory/batches/").json()["results"]]
        self.assertNotIn(theirs.id, ids)
        self.assertEqual(c.get(f"/api/inventory/batches/{theirs.id}/").status_code, 404)
        self.assertEqual(c.post(f"/api/inventory/batches/{theirs.id}/adjust/", {"quantity": 1}, format="json").status_code, 404)
        self.assertEqual(c.post("/api/marketplace/listings/from-batch/", {"batch": theirs.id}, format="json").status_code, 403)

    def test_role_permissions(self):
        ngo = self.api(self.u_ngo)
        self.assertEqual(ngo.get("/api/inventory/batches/").status_code, 403)
        self.assertEqual(ngo.get("/api/analytics/business/").status_code, 403)
        self.assertEqual(self.api(self.u_biz).get("/api/analytics/ngo/").status_code, 403)
        self.assertEqual(self.api(self.u_biz).get("/api/marketplace/listings/feed/").status_code, 403)
        self.assertEqual(self.api(self.u_biz).get("/api/analytics/admin/").status_code, 403)
        self.assertEqual(self.api(self.admin).get("/api/analytics/admin/").status_code, 200)

    def test_anonymous_is_rejected(self):
        for url in ["/api/inventory/batches/", "/api/marketplace/listings/", "/api/pickups/", "/api/notifications/"]:
            self.assertEqual(self.api().get(url).status_code, 401, url)

    def test_internal_endpoints_need_service_key(self):
        anon = self.api()
        self.assertIn(anon.get("/api/internal/inventory-snapshot/").status_code, (401, 403))
        ok = anon.get("/api/internal/inventory-snapshot/", HTTP_X_SERVICE_KEY="dev-service-key")
        self.assertEqual(ok.status_code, 200)

    def test_notifications_are_private(self):
        from core.services import notify
        notify(self.biz2, "secret", email=False)
        titles = [n["title"] for n in self.api(self.u_biz).get("/api/notifications/").json()["results"]]
        self.assertNotIn("secret", titles)

    def test_login_flow(self):
        r = self.api().post("/api/auth/login/", {"email": "owner@bistro.test", "password": "Pass@12345"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        tok = r.json()["access"]
        me = self.api()
        me.credentials(HTTP_AUTHORIZATION=f"Bearer {tok}")
        self.assertEqual(me.get("/api/auth/me/").json()["organization"]["id"], self.biz.id)
        bad = self.api().post("/api/auth/login/", {"email": "owner@bistro.test", "password": "nope"}, format="json")
        self.assertIn(bad.status_code, (400, 401))

    def test_run_jobs_endpoint_for_free_hosting(self):
        from inventory.models import ExpiryAlert
        self.stock(qty=2, days=0)
        anon = self.api()
        self.assertIn(anon.post("/api/internal/run-jobs/").status_code, (401, 403))
        r = anon.post("/api/internal/run-jobs/?risk=1", HTTP_X_SERVICE_KEY="dev-service-key")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["jobs"], {"expiry_scan": "ok", "pickups": "ok", "risk_scoring": "ok"})
        self.assertTrue(ExpiryAlert.objects.filter(organization=self.biz).exists())

    def test_database_url_parsing(self):
        import importlib
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"DATABASE_URL": "postgresql://u%40x:p%23w@db.example.com:6543/fb?sslmode=require"}):
            import config.settings as s
            s = importlib.reload(s)
            db = s.DATABASES["default"]
        importlib.reload(s)
        self.assertEqual((db["USER"], db["PASSWORD"], db["HOST"], db["PORT"], db["NAME"]),
                         ("u@x", "p#w", "db.example.com", "6543", "fb"))
        self.assertEqual(db["OPTIONS"], {"sslmode": "require"})
