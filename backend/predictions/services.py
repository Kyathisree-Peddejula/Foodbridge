import logging

from django.utils import timezone

from core.models import Notification
from core.services import notify
from inventory.models import InventoryBatch, Product
from predictions import client, heuristics
from predictions.models import PredictionRun, ReorderRecommendation
from predictions.payloads import batch_items, reorder_items, scorable_batches

log = logging.getLogger(__name__)


def apply_scores(results, run=None):
    """Write risk results onto batches and notify about newly high/critical items."""
    by_id = {r["batch_id"]: r for r in results}
    batches = InventoryBatch.objects.select_related("product", "organization").filter(id__in=by_id)
    escalated = {}
    now = timezone.now()
    for b in batches:
        r = by_id[b.id]
        was = b.risk_level
        b.risk_score = r["risk_score"]
        b.risk_level = r["risk_level"]
        b.predicted_demand = r.get("predicted_demand")
        b.expected_waste_qty = r.get("expected_waste_qty")
        b.recommended_action = (r.get("recommended_action") or "")[:200]
        b.risk_factors = r.get("factors", {})
        b.risk_model = (r.get("model") or "")[:40]
        b.risk_updated_at = now
        b.save(update_fields=["risk_score", "risk_level", "predicted_demand", "expected_waste_qty",
                              "recommended_action", "risk_factors", "risk_model", "risk_updated_at"])
        if b.risk_level in ("high", "critical") and was not in ("high", "critical"):
            escalated.setdefault(b.organization, []).append(b)
    for org, items in escalated.items():
        lines = [f"{b.product.name}: risk {b.risk_score:.0f} · ~{b.expected_waste_qty or 0:g} {b.product.unit} "
                 f"may go unsold · {b.recommended_action}" for b in items[:15]]
        notify(org, f"{len(items)} item(s) at high waste risk", "\n".join(lines),
               kind=Notification.Kind.RISK, link="/predictions")
    high = sum(1 for r in results if r["risk_level"] in ("high", "critical"))
    if run:
        run.items_scored, run.high_risk_items = len(results), high
        run.status, run.finished_at = "done", now
        run.save()
    return {"scored": len(results), "high_risk": high}


def refresh_risk(org=None, source=PredictionRun.Source.ON_DEMAND, batch_ids=None):
    qs = scorable_batches(org)
    if batch_ids:
        qs = qs.filter(id__in=batch_ids)
    items = batch_items(qs)
    run = PredictionRun.objects.create(organization=org, source=source)
    if not items:
        run.status, run.finished_at = "done", timezone.now()
        run.save()
        return run, {"scored": 0, "high_risk": 0}
    try:
        results = client.score_batch(items)
        run.engine = "ml-service"
    except client.MLServiceError as exc:
        results = [heuristics.score_item(it) for it in items]
        run.engine = "fallback-heuristic"
        run.detail = {"ml_error": str(exc)[:300]}
    return run, apply_scores(results, run)


def recommend_reorders(org, product_ids=None):
    products = Product.objects.filter(organization=org, is_active=True).select_related("category")
    if product_ids:
        products = products.filter(id__in=product_ids)
    items, cfg = reorder_items(org, list(products))
    if not items:
        return []
    try:
        results = client.reorder(items, cfg)
        engine = "ml-service"
    except client.MLServiceError:
        results = [heuristics.reorder_item(it, cfg) for it in items]
        engine = "fallback-heuristic"
    ReorderRecommendation.objects.filter(organization=org, product_id__in=[i["product_id"] for i in items]).delete()
    objs = [ReorderRecommendation(
        organization=org, product_id=r["product_id"], current_stock=r["current_stock"],
        forecast_demand=r["forecast_demand"], safety_stock=r.get("safety_stock", 0),
        recommended_qty=r["recommended_qty"], max_by_shelf_life=r.get("max_by_shelf_life"),
        max_by_capacity=r.get("max_by_capacity"), naive_order_qty=r.get("naive_order_qty"),
        expected_waste_avoided=r.get("expected_waste_avoided", 0), urgency=r.get("urgency", "normal"),
        rationale=r.get("rationale", ""), engine=r.get("model", engine)[:24]) for r in results]
    return ReorderRecommendation.objects.bulk_create(objs)
