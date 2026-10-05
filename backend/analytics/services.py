"""Aggregations for the business, NGO, sustainability-impact and admin dashboards."""
from collections import defaultdict
from datetime import date, timedelta

from django.conf import settings
from django.db.models import Count, F, FloatField, Q, Sum
from django.db.models.functions import Coalesce, TruncMonth, TruncWeek
from django.utils import timezone

from accounts.models import Organization
from inventory.models import ExpiryAlert, InventoryBatch, Product, StockTransaction
from marketplace.models import Pickup, SurplusListing

KG_PER_MEAL = settings.IMPACT["KG_PER_MEAL"]
DEFAULT_CO2 = settings.IMPACT["DEFAULT_CO2E_PER_KG"]


def _weight_expr():
    return F("quantity") * Coalesce(F("product__unit_weight_kg"), 1.0)


def impact_from_pickups(qs):
    """kg diverted, CO2e avoided, meals — from completed pickups."""
    rows = qs.filter(status="completed").values(
        "listing__category__name", "listing__category__co2e_per_kg", "listing__category__color").annotate(
        kg=Coalesce(Sum("quantity_received_kg"), 0.0), meals=Coalesce(Sum("meals_served"), 0),
        people=Coalesce(Sum("beneficiaries_served"), 0), n=Count("id"))
    total_kg = co2 = meals = people = n = 0
    by_cat = []
    for r in rows:
        factor = r["listing__category__co2e_per_kg"] or DEFAULT_CO2
        kg = r["kg"]
        total_kg += kg
        co2 += kg * factor
        meals += r["meals"] or int(kg / KG_PER_MEAL)
        people += r["people"]
        n += r["n"]
        by_cat.append({"category": r["listing__category__name"] or "Other", "color": r["listing__category__color"],
                       "kg": round(kg, 1), "co2e_kg": round(kg * factor, 1)})
    by_cat.sort(key=lambda x: -x["kg"])
    return {"food_diverted_kg": round(total_kg, 1), "co2e_avoided_kg": round(co2, 1), "meals": int(meals),
            "beneficiaries": int(people), "pickups_completed": n, "by_category": by_cat}


def monthly_trend(pickups, months=6):
    start = (timezone.localdate().replace(day=1) - timedelta(days=31 * (months - 1))).replace(day=1)
    rows = (pickups.filter(status="completed", delivered_at__date__gte=start)
            .annotate(m=TruncMonth("delivered_at")).values("m")
            .annotate(kg=Coalesce(Sum("quantity_received_kg"), 0.0), meals=Coalesce(Sum("meals_served"), 0),
                      co2=Coalesce(Sum(F("quantity_received_kg") * Coalesce(F("listing__category__co2e_per_kg"),
                                                                              DEFAULT_CO2),
                                       output_field=FloatField()), 0.0)).order_by("m"))
    by_m = {r["m"].date().replace(day=1) if hasattr(r["m"], "date") else r["m"]: r for r in rows}
    out, cur = [], start
    for _ in range(months):
        r = by_m.get(cur, {})
        out.append({"month": cur.strftime("%b %Y"), "kg": round(r.get("kg", 0), 1),
                    "meals": int(r.get("meals", 0)), "co2e_kg": round(r.get("co2", 0), 1)})
        cur = (cur + timedelta(days=32)).replace(day=1)
    return out


def business_dashboard(org):
    today = timezone.localdate()
    batches = InventoryBatch.objects.filter(organization=org, quantity__gt=0).select_related("product__category")
    live = batches.exclude(status="depleted")
    status_counts = {r["status"]: r["n"] for r in live.values("status").annotate(n=Count("id"))}
    risk_counts = {r["risk_level"]: r["n"] for r in live.values("risk_level").annotate(n=Count("id"))}
    value = sum(b.value for b in live)
    at_risk_value = sum(float(b.product.unit_cost) * (b.expected_waste_qty or 0) for b in live
                        if b.risk_level in ("high", "critical"))
    at_risk_kg = sum((b.expected_waste_qty or 0) * (b.product.unit_weight_kg or 1) for b in live
                     if b.risk_level in ("high", "critical"))
    expiring_3 = live.filter(expiry_date__lte=today + timedelta(days=3), expiry_date__gte=today).count()

    # weekly movement: sold vs wasted vs donated (kg), last 8 weeks
    since = timezone.now() - timedelta(weeks=8)
    moves = (StockTransaction.objects.filter(organization=org, occurred_at__gte=since,
                                             txn_type__in=["sale", "waste", "donation"])
             .annotate(w=TruncWeek("occurred_at")).values("w", "txn_type")
             .annotate(kg=Sum(F("quantity") * Coalesce(F("product__unit_weight_kg"), 1.0),
                              output_field=FloatField())).order_by("w"))
    weeks = defaultdict(lambda: {"sale": 0, "waste": 0, "donation": 0})
    for r in moves:
        weeks[r["w"].date()][r["txn_type"]] += r["kg"] or 0
    week_list = []
    start = (timezone.localdate() - timedelta(days=timezone.localdate().weekday())) - timedelta(weeks=7)
    for i in range(8):
        wk = start + timedelta(weeks=i)
        v = weeks.get(wk, {"sale": 0, "waste": 0, "donation": 0})
        tot = v["sale"] + v["waste"] + v["donation"]
        week_list.append({"week": wk.strftime("%d %b"), "sold_kg": round(v["sale"], 1),
                          "wasted_kg": round(v["waste"], 1), "donated_kg": round(v["donation"], 1),
                          "waste_rate": round(100 * v["waste"] / tot, 1) if tot else 0})

    # risk by category for the chart
    cat_rows = defaultdict(lambda: {"batches": 0, "risk_sum": 0.0, "scored": 0, "kg": 0.0, "color": "#999"})
    for b in live:
        name = b.product.category.name if b.product.category else "Other"
        c = cat_rows[name]
        c["batches"] += 1
        c["kg"] += b.weight_kg
        c["color"] = b.product.category.color if b.product.category else "#999"
        if b.risk_score is not None:
            c["risk_sum"] += b.risk_score
            c["scored"] += 1
    by_cat = sorted([{"category": k, "batches": v["batches"], "stock_kg": round(v["kg"], 1), "color": v["color"],
                      "avg_risk": round(v["risk_sum"] / v["scored"], 1) if v["scored"] else None}
                     for k, v in cat_rows.items()], key=lambda x: -(x["avg_risk"] or 0))

    listings = SurplusListing.objects.filter(donor=org)
    pickups = Pickup.objects.filter(listing__donor=org)
    impact = impact_from_pickups(pickups)
    month_start = today.replace(day=1)
    month_kg = pickups.filter(status="completed", delivered_at__date__gte=month_start).aggregate(
        s=Coalesce(Sum("quantity_received_kg"), 0.0))["s"]

    return {
        "kpis": {
            "products": Product.objects.filter(organization=org, is_active=True).count(),
            "active_batches": live.count(), "stock_value": round(value, 2),
            "value_at_risk": round(at_risk_value, 2), "kg_at_risk": round(at_risk_kg, 1),
            "expiring_3_days": expiring_3,
            "high_risk": risk_counts.get("high", 0) + risk_counts.get("critical", 0),
            "open_alerts": ExpiryAlert.objects.filter(organization=org, is_acknowledged=False).count(),
            "donated_this_month_kg": round(month_kg, 1),
            "co2e_avoided_kg": impact["co2e_avoided_kg"], "meals_donated": impact["meals"],
        },
        "inventory_health": {k: status_counts.get(k, 0) for k in ["active", "expiring", "expired", "listed"]},
        "risk_distribution": {k: risk_counts.get(k, 0) for k in ["critical", "high", "medium", "low", "unknown"]},
        "risk_by_category": by_cat,
        "weekly_flow": week_list,
        "donation_tracker": {
            "listings": {k: listings.filter(status=k).count() for k in
                         ["available", "reserved", "completed", "expired", "cancelled"]},
            "pickups": {k: pickups.filter(status=k).count() for k in
                        ["requested", "confirmed", "in_transit", "completed", "cancelled"]},
            "recent": [{"id": p.id, "title": p.listing.title, "ngo": p.ngo.name, "kg": p.quantity_kg,
                        "status": p.status, "when": p.scheduled_start}
                       for p in pickups.select_related("listing", "ngo").order_by("-scheduled_start")[:8]],
        },
        "impact": impact,
    }


def ngo_dashboard(org):
    pickups = Pickup.objects.filter(ngo=org).select_related("listing__donor", "listing__category")
    impact = impact_from_pickups(pickups)
    upcoming = pickups.filter(status__in=["requested", "confirmed", "in_transit"]).order_by("scheduled_start")
    history = pickups.filter(status__in=["completed", "cancelled", "no_show"]).order_by("-scheduled_start")
    from marketplace.models import Match
    available = Match.objects.filter(ngo=org, listing__status="available",
                                     listing__expiry_date__gte=timezone.localdate()).exclude(status="declined")
    donors = (pickups.filter(status="completed").values("listing__donor__name")
              .annotate(kg=Sum("quantity_received_kg"), n=Count("id")).order_by("-kg")[:5])

    def row(p):
        return {"id": p.id, "title": p.listing.title, "donor": p.listing.donor.name,
                "category": p.listing.category.name if p.listing.category else None, "kg": p.quantity_kg,
                "received_kg": p.quantity_received_kg, "status": p.status, "start": p.scheduled_start,
                "end": p.scheduled_end, "address": p.listing.pickup_address, "meals": p.meals_served}

    return {
        "kpis": {"matched_donations": available.count(),
                 "high_match_donations": available.filter(score__gte=70).count(),
                 "upcoming_pickups": upcoming.count(),
                 "food_received_kg": impact["food_diverted_kg"], "meals_served": impact["meals"],
                 "beneficiaries_reached": impact["beneficiaries"] or org.beneficiaries,
                 "co2e_avoided_kg": impact["co2e_avoided_kg"], "reliability": org.reliability_score},
        "incoming": [row(p) for p in upcoming[:10]],
        "history": [row(p) for p in history[:15]],
        "by_category": impact["by_category"],
        "monthly": monthly_trend(pickups),
        "top_donors": [{"donor": d["listing__donor__name"], "kg": round(d["kg"] or 0, 1), "pickups": d["n"]}
                       for d in donors],
    }


def impact_dashboard(org=None):
    pickups = Pickup.objects.all()
    if org is not None:
        pickups = pickups.filter(Q(ngo=org) | Q(listing__donor=org))
    impact = impact_from_pickups(pickups)
    wasted = StockTransaction.objects.filter(txn_type="waste")
    if org is not None:
        wasted = wasted.filter(organization=org)
    wasted_kg = wasted.aggregate(s=Coalesce(Sum(F("quantity") * Coalesce(F("product__unit_weight_kg"), 1.0),
                                                output_field=FloatField()), 0.0))["s"]
    diverted = impact["food_diverted_kg"]
    return {
        **impact,
        "wasted_kg": round(wasted_kg, 1),
        "diversion_rate": round(100 * diverted / (diverted + wasted_kg), 1) if (diverted + wasted_kg) else 0,
        "equivalents": {"car_km_avoided": round(impact["co2e_avoided_kg"] / 0.17, 0),
                        "trees_year": round(impact["co2e_avoided_kg"] / 21.0, 1)},
        "monthly": monthly_trend(pickups, months=6),
        "methodology": {"kg_per_meal": KG_PER_MEAL, "co2e": "category factor (kg CO2e per kg food) from taxonomy",
                        "car_km": "0.17 kg CO2e per km", "tree": "21 kg CO2 absorbed per tree per year"},
    }


def admin_overview(days=30):
    since = timezone.now() - timedelta(days=days)
    pickups = Pickup.objects.all()
    impact = impact_from_pickups(pickups)
    recent_impact = impact_from_pickups(pickups.filter(delivered_at__gte=since))
    donors = (pickups.filter(status="completed", delivered_at__gte=since).values("listing__donor__name")
              .annotate(kg=Sum("quantity_received_kg")).order_by("-kg")[:5])
    recent = Pickup.objects.select_related("listing__donor", "listing__category", "ngo").order_by("-created_at")[:10]
    return {
        "kpis": {"listings_active": SurplusListing.objects.filter(status="available").count(),
                 "donors": Organization.objects.filter(org_type="business").count(),
                 "food_rescued_kg": impact["food_diverted_kg"], "food_rescued_period_kg":
                     recent_impact["food_diverted_kg"], "co2e_avoided_kg": impact["co2e_avoided_kg"],
                 "ngos_active": Organization.objects.filter(org_type="ngo").count(), "meals": impact["meals"]},
        "rescued_by_category": recent_impact["by_category"],
        "top_donors": [{"donor": d["listing__donor__name"], "kg": round(d["kg"] or 0, 1)} for d in donors],
        "recent_operations": [{"pickup_id": p.id, "listing_id": f"LST-{p.listing_id:04d}", "donor": p.listing.donor.name,
                               "food_type": p.listing.category.name if p.listing.category else "Other",
                               "kg": p.quantity_kg, "ngo": p.ngo.name, "status": p.status} for p in recent],
        "monthly": monthly_trend(pickups),
    }
