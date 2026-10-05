"""Waste risk scoring: combines days-to-expiry, current stock and the demand forecast.

For every batch we estimate how much of it will sell before it expires using the demand
forecast. Batches of the same product share demand in FIFO order (earliest expiry sells first),
so two batches of milk don't both "claim" tomorrow's sales.

    surplus_ratio   = expected unsold qty / qty                       (0..1)
    expiry_urgency  = exp(-days_to_expiry / tau[perishability])       (0..1)
    cover_term      = logistic(stock cover days / days left - 1)      (0..1)
    waste_prob      = P(demand over shelf-life window < qty)          (0..1, normal approx w/ model error)

    risk = 100 * (0.45 surplus + 0.25 urgency + 0.15 cover + 0.15 waste_prob)
"""
from __future__ import annotations

import math
from collections import defaultdict

from app.forecaster import service

TAU = {"high": 2.0, "medium": 4.0, "low": 10.0}
WEIGHTS = {"surplus_ratio": 0.45, "expiry_urgency": 0.25, "cover": 0.15, "waste_probability": 0.15}


def level_for(score: float) -> str:
    return "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 35 else "low"


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _action(level, unsold, qty, days, unit, surplus_ratio):
    if level == "critical":
        return f"Donate ~{unsold:g} {unit} now via the marketplace (sells {qty - unsold:g} before expiry)"
    if level == "high":
        disc = min(50, max(15, round(surplus_ratio * 60 / 5) * 5))
        return f"Discount {disc}% today; list ~{unsold:g} {unit} for donation if unsold in {max(days - 1, 0)}d"
    if level == "medium":
        return "Move to front shelf, bundle offers, re-check tomorrow"
    return "No action needed"


def _demand_window(item, days):
    """Forecast demand for the remaining sellable days (fractional last day)."""
    horizon = max(1, math.ceil(days + 0.5))
    fc = service.forecast(item, horizon) if service.ready else None
    if fc:
        daily = fc["daily"]
        frac = (days + 0.5) - (horizon - 1)
        demand = sum(daily[:horizon - 1]) + daily[horizon - 1] * min(max(frac, 0), 1)
        return demand, daily, fc["model"], fc.get("expected_error_wape", 0.35)
    hist = item.get("recent_daily_sales") or []
    rate = sum(hist[-14:]) / len(hist[-14:]) if hist else 0.0
    return rate * (days + 0.5), [rate] * horizon, "moving-average", 0.4


def score_items(items: list[dict]) -> list[dict]:
    groups = defaultdict(list)
    for it in items:
        groups[(it.get("organization_id"), it.get("product_id"))].append(it)
    out = []
    for _, batch in groups.items():
        batch.sort(key=lambda x: x["days_to_expiry"])
        consumed = 0.0  # demand already absorbed by earlier-expiring batches of the same product
        for it in batch:
            r, used = _score_one(it, consumed)
            consumed += used
            out.append(r)
    order = {it["batch_id"]: i for i, it in enumerate(items)}
    return sorted(out, key=lambda r: order.get(r["batch_id"], 0))


def score_one(item: dict) -> dict:
    return _score_one(item, 0.0)[0]


def _score_one(it: dict, consumed_before: float):
    qty = float(it["quantity"])
    days = int(it["days_to_expiry"])
    unit = it.get("unit") or "units"
    base = {"batch_id": it.get("batch_id"), "product_id": it.get("product_id")}
    if qty <= 1e-9:  # nothing on hand -> nothing can be wasted
        return {**base, "risk_score": 0.0, "risk_level": "low", "predicted_demand": 0.0,
                "expected_waste_qty": 0.0, "recommended_action": "No stock on hand",
                "model": "rule", "factors": {"empty": True}}, 0.0
    if days < 0:
        return {**base, "risk_score": 100.0, "risk_level": "critical", "predicted_demand": 0.0,
                "expected_waste_qty": qty, "recommended_action": "Expired: remove from sale and log as waste",
                "model": "rule", "factors": {"expired": True}}, 0.0
    demand, daily, model, wape = _demand_window(it, days)
    available_demand = max(0.0, demand - consumed_before)
    sold = min(qty, available_demand)
    unsold = max(0.0, qty - sold)
    surplus_ratio = unsold / qty if qty else 0.0
    urgency = math.exp(-days / TAU.get(it.get("perishability") or "medium", 4.0))
    rate = (sum(daily) / len(daily)) if daily else 0.0
    window = days + 0.5
    cover = (qty / rate) / window if rate > 0 else 3.0
    cover_term = 1 / (1 + math.exp(-2 * (cover - 1)))
    sigma = max(available_demand * max(wape, 0.1), 0.5)
    waste_prob = 1 - _phi((available_demand - qty) / sigma)
    score = 100 * (WEIGHTS["surplus_ratio"] * surplus_ratio + WEIGHTS["expiry_urgency"] * urgency
                   + WEIGHTS["cover"] * cover_term + WEIGHTS["waste_probability"] * waste_prob)
    if unsold <= 0.01 and days > 1:  # fully covered by demand: cap so it never shouts "donate"
        score = min(score, 45.0)
    score = round(min(100.0, score), 1)
    level = level_for(score)
    unsold_r = round(unsold, 2)
    return {**base, "risk_score": score, "risk_level": level, "predicted_demand": round(available_demand, 2),
            "expected_waste_qty": unsold_r,
            "recommended_action": _action(level, unsold_r, qty, days, unit, surplus_ratio),
            "model": model,
            "factors": {"surplus_ratio": round(surplus_ratio, 3), "expiry_urgency": round(urgency, 3),
                        "cover_ratio": round(cover, 2), "waste_probability": round(waste_prob, 3),
                        "daily_demand": round(rate, 3), "days_to_expiry": days,
                        "demand_shared_with_earlier_batches": round(min(consumed_before, demand), 2),
                        "weights": WEIGHTS}}, sold
