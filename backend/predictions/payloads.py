"""Builds the JSON the ML service expects from Django inventory rows."""
from datetime import date, timedelta

from django.db.models import Sum
from django.db.models.functions import TruncDate

from inventory.models import InventoryBatch, Product, StockTransaction
from django.utils import timezone

HISTORY_DAYS = 28


def daily_sales(product_ids, days=HISTORY_DAYS):
    """{product_id: [qty day -days .. yesterday]} built from sale transactions."""
    start = timezone.localdate() - timedelta(days=days)
    rows = (StockTransaction.objects.filter(product_id__in=product_ids, txn_type="sale",
                                            occurred_at__date__gte=start, occurred_at__date__lt=timezone.localdate())
            .annotate(d=TruncDate("occurred_at")).values("product_id", "d").annotate(q=Sum("quantity")))
    out = {pid: [0.0] * days for pid in product_ids}
    for r in rows:
        idx = (r["d"] - start).days
        if 0 <= idx < days:
            out[r["product_id"]][idx] = float(r["q"])
    return out


def product_context(p, org):
    cat = p.category
    return {
        "product_id": p.id, "product_name": p.name, "unit": p.unit,
        "category_slug": cat.slug if cat else None,
        "perishability": cat.perishability if cat else "medium",
        "shelf_life_days": p.effective_shelf_life,
        "fr_store_id": org.fr_store_id, "fr_product_id": p.fr_product_id,
        "fr_first_category_id": p.fr_first_category_id,
    }


def batch_items(batches):
    batches = list(batches.select_related("product__category", "organization"))
    sales = daily_sales({b.product_id for b in batches})
    items = []
    for b in batches:
        items.append({
            "batch_id": b.id, "organization_id": b.organization_id,
            **product_context(b.product, b.organization),
            "quantity": b.quantity, "days_to_expiry": b.days_to_expiry,
            "expiry_date": b.expiry_date.isoformat(), "recent_daily_sales": sales[b.product_id],
            "unit_weight_kg": b.product.unit_weight_kg,
        })
    return items


def scorable_batches(org=None):
    qs = InventoryBatch.objects.filter(quantity__gt=0).exclude(status=InventoryBatch.Status.DEPLETED)
    return qs.filter(organization=org) if org else qs


def reorder_items(org, products=None):
    products = list(products or Product.objects.filter(organization=org, is_active=True).select_related("category"))
    sales = daily_sales({p.id for p in products})
    stock = dict(InventoryBatch.objects.filter(product__in=products, quantity__gt=0)
                 .values_list("product_id").annotate(s=Sum("quantity")))
    used_space = sum(stock.get(p.id, 0) * p.storage_space_per_unit_kg for p in products)
    items = [{
        **product_context(p, org), "current_stock": float(stock.get(p.id, 0)),
        "recent_daily_sales": sales[p.id], "storage_space_per_unit": p.storage_space_per_unit_kg,
    } for p in products]
    return items, {"lead_time_days": org.reorder_lead_time_days, "review_period_days": 1,
                   "storage_capacity": org.storage_capacity_kg, "storage_used": used_space}
