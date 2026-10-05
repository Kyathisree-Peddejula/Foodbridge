"""Fallback scoring used when the ML microservice is unreachable (same formula, naive demand)."""
import math

TAU = {"high": 2.0, "medium": 4.0, "low": 10.0}


def naive_rate(sales):
    recent = [s for s in sales[-14:]]
    return (sum(recent) / len(recent)) if recent else 0.0


def score_item(it):
    rate = naive_rate(it.get("recent_daily_sales") or [])
    days = it["days_to_expiry"]
    qty = it["quantity"]
    if days < 0:
        return {"batch_id": it["batch_id"], "risk_score": 100.0, "risk_level": "critical", "predicted_demand": 0,
                "expected_waste_qty": qty, "recommended_action": "Expired: remove from sale and log as waste",
                "model": "fallback-heuristic", "factors": {"expired": True}}
    horizon = max(days, 0) + 0.5
    demand = rate * horizon
    unsold = max(0.0, qty - demand)
    surplus_ratio = unsold / qty if qty else 0
    urgency = math.exp(-max(days, 0) / TAU.get(it.get("perishability"), 4.0))
    cover = (qty / rate) / horizon if rate > 0 else 3.0
    cover_term = 1 / (1 + math.exp(-2 * (cover - 1)))
    score = round(100 * (0.5 * surplus_ratio + 0.3 * urgency + 0.2 * cover_term), 1)
    level = "critical" if score >= 80 else "high" if score >= 60 else "medium" if score >= 35 else "low"
    action = ("Donate surplus now" if level == "critical" else "Discount or list surplus for donation"
              if level == "high" else "Place at front, monitor daily" if level == "medium" else "No action needed")
    return {"batch_id": it["batch_id"], "risk_score": score, "risk_level": level,
            "predicted_demand": round(demand, 2), "expected_waste_qty": round(unsold, 2),
            "recommended_action": action, "model": "fallback-heuristic",
            "factors": {"surplus_ratio": round(surplus_ratio, 3), "expiry_urgency": round(urgency, 3),
                        "cover_ratio": round(cover, 2), "daily_demand": round(rate, 3)}}


def reorder_item(it, cfg):
    rate = naive_rate(it["recent_daily_sales"])
    period = cfg["lead_time_days"] + cfg["review_period_days"]
    demand = rate * period
    hist = it["recent_daily_sales"][-14:]
    mean = rate
    sd = math.sqrt(sum((x - mean) ** 2 for x in hist) / len(hist)) if hist else 0
    safety = 1.28 * sd * math.sqrt(period)
    qty = max(0.0, demand + safety - it["current_stock"])
    qty = min(qty, rate * it["shelf_life_days"]) if rate else qty
    return {"product_id": it["product_id"], "current_stock": it["current_stock"], "forecast_demand": round(demand, 2),
            "safety_stock": round(safety, 2), "recommended_qty": round(qty, 1),
            "max_by_shelf_life": round(rate * it["shelf_life_days"], 1), "max_by_capacity": None,
            "naive_order_qty": round(max(0.0, rate * 7 - it["current_stock"]), 1), "expected_waste_avoided": 0,
            "urgency": "high" if it["current_stock"] < demand else "normal",
            "rationale": "Moving-average estimate (ML service offline).", "model": "fallback-heuristic"}
