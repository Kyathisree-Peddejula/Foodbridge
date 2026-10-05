"""Weeks 3-4 integration from the Django side: risk scoring, reorder, forecasts, ML-offline fallback."""
from inventory.models import InventoryBatch
from predictions.models import PredictionRun

from .base import FBTestCase, live_ml_service


class FallbackTests(FBTestCase):
    """ML service unreachable → heuristics keep the product working."""

    def test_risk_refresh_falls_back(self):
        b = self.stock(qty=80, days=1)
        r = self.api(self.u_biz).post("/api/predictions/risk/refresh/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["engine"], "fallback-heuristic")
        b.refresh_from_db()
        self.assertIsNotNone(b.risk_score)
        self.assertIn(b.risk_level, ("low", "medium", "high", "critical"))

    def test_reorder_and_forecast_fall_back(self):
        p = self.product()
        self.stock(qty=5, product=p)
        c = self.api(self.u_biz)
        self.assertEqual(c.post("/api/predictions/reorder/", {}, format="json").status_code, 201)
        f = c.get(f"/api/predictions/forecast/{p.id}/?horizon=7")
        self.assertEqual(f.status_code, 200, f.content)
        self.assertEqual(len(f.json()["daily"]), 7)

    def test_model_status_reports_offline(self):
        r = self.api(self.u_biz).get("/api/predictions/model-status/").json()
        self.assertFalse(r["online"])

    def test_bad_horizon_is_400(self):
        p = self.product()
        self.assertEqual(self.api(self.u_biz).get(f"/api/predictions/forecast/{p.id}/?horizon=abc").status_code, 400)

    def test_forecast_for_foreign_product_404(self):
        p = self.product(org=self.biz2, name="x")
        self.assertEqual(self.api(self.u_biz).get(f"/api/predictions/forecast/{p.id}/").status_code, 404)


class LiveMLTests(FBTestCase):
    """Django ↔ FastAPI contract, using the real trained models in-process."""

    def test_risk_refresh_uses_ml_service(self):
        big = self.stock(qty=200, days=1, name="Biryani", slug="cooked-meals", unit="portion", sku="BIR")
        small = self.stock(qty=1, days=5, name="Butter", sku="BUT")
        with live_ml_service():
            r = self.api(self.u_biz).post("/api/predictions/risk/refresh/", {}, format="json").json()
        self.assertEqual(r["engine"], "ml-service")
        big.refresh_from_db(), small.refresh_from_db()
        self.assertGreater(big.risk_score, small.risk_score)
        self.assertTrue(big.recommended_action)

    def test_ingest_endpoint_used_by_scheduled_batch(self):
        b = self.stock(qty=10, days=2)
        snap = self.api().get("/api/internal/inventory-snapshot/", HTTP_X_SERVICE_KEY="dev-service-key").json()
        self.assertIn(b.id, [i["batch_id"] for i in snap["items"]])
        body = {"results": [{"batch_id": b.id, "product_id": b.product_id, "risk_score": 77, "risk_level": "high",
                             "predicted_demand": 1, "expected_waste_qty": 8, "recommended_action": "Donate",
                             "model": "ensemble", "factors": {}}]}
        r = self.api().post(f"/api/internal/risk-scores/?run_id={snap['run_id']}", body, format="json",
                            HTTP_X_SERVICE_KEY="dev-service-key")
        self.assertEqual(r.status_code, 200, r.content)
        b.refresh_from_db()
        self.assertEqual((b.risk_score, b.risk_level), (77, "high"))
        run = PredictionRun.objects.get(pk=snap["run_id"])
        self.assertEqual((run.source, run.items_scored), ("scheduled", 1))
        bad = self.api().post("/api/internal/risk-scores/?run_id=abc", body, format="json",
                              HTTP_X_SERVICE_KEY="dev-service-key")
        self.assertEqual(bad.status_code, 200)   # unknown run id is tolerated, scores still applied

    def test_reorder_and_forecast_via_ml(self):
        p = self.product(name="Milk", unit="l")
        self.stock(qty=3, product=p)
        with live_ml_service():
            c = self.api(self.u_biz)
            rows = c.post("/api/predictions/reorder/", {}, format="json").json()
            f = c.get(f"/api/predictions/forecast/{p.id}/?horizon=14").json()
            st = c.get("/api/predictions/model-status/").json()
        self.assertTrue(rows)
        self.assertEqual(len(f["daily"]), 14)
        self.assertTrue(st["online"])
