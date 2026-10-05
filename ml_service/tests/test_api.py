"""FastAPI waste-prediction service: contract, edge cases and invariants."""
import math

import pytest

from tests.conftest import item


def test_health_and_models(client):
    assert client.get("/health").json()["status"] == "ok"
    m = client.get("/models").json()
    assert m["ready"] is True
    assert set(m["metrics"]) >= {"prophet", "lstm", "seasonal_naive"}


# ---------------------------------------------------------------- risk scoring
def score(client, **kw):
    r = client.post("/risk/score", json=item(**kw))
    assert r.status_code == 200, r.text
    return r.json()


def test_expired_batch_is_critical(client):
    r = score(client, days_to_expiry=-1)
    assert r["risk_score"] == 100 and r["risk_level"] == "critical"


def test_zero_quantity_is_not_risky(client):
    r = score(client, quantity=0)
    assert r["risk_score"] <= 5 and r["expected_waste_qty"] == 0


def test_risk_is_monotonic_in_stock(client):
    low = score(client, quantity=5)["risk_score"]
    high = score(client, quantity=500)["risk_score"]
    assert high > low


def test_risk_rises_as_expiry_nears(client):
    far = score(client, quantity=60, days_to_expiry=6)["risk_score"]
    near = score(client, quantity=60, days_to_expiry=0)["risk_score"]
    assert near > far


def test_no_sales_history_still_scores(client):
    r = score(client, recent_daily_sales=[], product_id=None)
    assert 0 <= r["risk_score"] <= 100 and not math.isnan(r["predicted_demand"])


def test_negative_quantity_rejected(client):
    assert client.post("/risk/score", json=item(quantity=-3)).status_code == 422


def test_batch_scoring_shares_demand_fifo(client):
    # two batches of the same product: the later-expiring one should not reuse the same demand
    a = item(batch_id=1, quantity=30, days_to_expiry=1)
    b = item(batch_id=2, quantity=30, days_to_expiry=3)
    res = client.post("/risk/score/batch", json={"items": [a, b]}).json()["results"]
    by = {r["batch_id"]: r for r in res}
    solo = score(client, batch_id=2, quantity=30, days_to_expiry=3)
    assert by[2]["expected_waste_qty"] >= solo["expected_waste_qty"] - 1e-6


def test_empty_batch_request(client):
    r = client.post("/risk/score/batch", json={"items": []})
    assert r.status_code == 200 and r.json()["results"] == []


# ---------------------------------------------------------------- reorder
def reorder(client, **kw):
    body = {"items": [{**item(), "current_stock": 0, **kw.pop("item", {})}], "lead_time_days": 2,
            "review_period_days": 1, **kw}
    r = client.post("/reorder/recommend", json=body)
    assert r.status_code == 200, r.text
    return r.json()["results"][0]


def test_reorder_respects_shelf_life(client):
    r = reorder(client, item={"shelf_life_days": 1})
    assert r["recommended_qty"] <= r["max_by_shelf_life"] + 1e-6


def test_reorder_zero_capacity(client):
    r = reorder(client, storage_capacity=100, storage_used=100)
    assert r["recommended_qty"] == 0


def test_reorder_never_negative_when_overstocked(client):
    r = reorder(client, item={"current_stock": 10_000})
    assert r["recommended_qty"] == 0


# ---------------------------------------------------------------- forecasting
def test_forecast_shapes(client):
    r = client.post("/forecast", json={**item(), "horizon_days": 14}).json()
    assert len(r["daily"]) == len(r["lower"]) == len(r["upper"]) == 14
    assert len(r["weekly"]) == 2
    assert all(lo <= d + 1e-6 <= up + 2e-6 for lo, d, up in zip(r["lower"], r["daily"], r["upper"]))
    assert all(v >= 0 for v in r["daily"])


def test_forecast_unknown_product_falls_back(client):
    r = client.post("/forecast", json={**item(product_id=987654, fr_product_id=None), "horizon_days": 7})
    assert r.status_code == 200 and len(r.json()["daily"]) == 7


@pytest.mark.parametrize("h", [0, 61])
def test_forecast_horizon_bounds(client, h):
    assert client.post("/forecast", json={**item(), "horizon_days": h}).status_code == 422
