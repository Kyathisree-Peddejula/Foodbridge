"""Smart reorder recommendations: forecast-driven order-up-to policy with shelf-life and storage caps.

    target      = forecast demand over (lead time + review period) + safety stock
    safety      = z(perishability) * sigma_daily * sqrt(L + R)   (lower service level for highly perishable
                  goods -> less over-stocking, since leftovers become waste)
    raw order   = max(0, target - current stock)
    shelf cap   = demand we can sell within one shelf life minus stock already on hand
    capacity    = if total recommended volume exceeds free storage, scale all orders proportionally
"""
from __future__ import annotations

import math

import numpy as np

from app.forecaster import service

Z = {"high": 0.84, "medium": 1.28, "low": 1.65}   # ~80%, 90%, 95% service levels


def _forecast(item, horizon):
    if service.ready:
        fc = service.forecast(item, horizon)
        return np.asarray(fc["daily"], float), fc["model"], fc.get("expected_error_wape", 0.35)
    hist = item.get("recent_daily_sales") or []
    rate = float(np.mean(hist[-14:])) if hist else 0.0
    return np.full(horizon, rate), "moving-average", 0.4


def recommend(items, lead_time_days=1, review_period_days=1, storage_capacity=None, storage_used=0.0):
    L, R = max(0, int(lead_time_days)), max(1, int(review_period_days))
    period = L + R
    rows = []
    for it in items:
        shelf = max(1, int(it.get("shelf_life_days") or 7))
        horizon = max(period, shelf, 7)
        daily, model, wape = _forecast(it, horizon)
        hist = np.asarray(it.get("recent_daily_sales") or [], float)
        demand_period = float(daily[:period].sum())
        sd_hist = float(hist[-14:].std()) if hist.size >= 3 else 0.0
        sd = max(sd_hist, float(daily[:period].mean()) * wape)
        z = Z.get(it.get("perishability") or "medium", 1.28)
        safety = z * sd * math.sqrt(period)
        stock = float(it.get("current_stock") or 0)
        raw = max(0.0, demand_period + safety - stock)
        # never buy more than can be sold within one shelf life after arrival
        max_shelf = max(0.0, float(daily[L:L + shelf].sum()) - max(0.0, stock - demand_period * L / period))
        qty = min(raw, max_shelf)
        naive = max(0.0, float(hist[-7:].mean()) * 7 - stock) if hist.size else 0.0  # "last week's sales" rule
        rows.append({"it": it, "qty": qty, "raw": raw, "max_shelf": max_shelf, "demand": demand_period,
                     "safety": safety, "stock": stock, "naive": naive, "model": model, "daily_mean": float(daily[:period].mean()),
                     "shelf": shelf})
    # storage capacity constraint (kg or storage units)
    cap_scale, free = 1.0, None
    if storage_capacity:
        free = max(0.0, float(storage_capacity) - float(storage_used or 0))
        need = sum(r["qty"] * float(r["it"].get("storage_space_per_unit") or 1) for r in rows)
        if need > free and need > 0:
            cap_scale = free / need
    out = []
    for r in rows:
        it = r["it"]
        space = float(it.get("storage_space_per_unit") or 1)
        qty = r["qty"] * cap_scale
        if it.get("unit") in (None, "pcs", "units", "pack", "box", "bottle", "loaf", "dozen", "tray"):
            qty = math.floor(qty) if cap_scale < 1 else math.ceil(qty - 1e-9)
        qty = max(0.0, float(qty))
        max_cap = (free / space) if free is not None and space else None
        # waste the naive order would create beyond what sells within shelf life
        waste_avoided = max(0.0, r["naive"] - r["max_shelf"]) if r["naive"] > qty else 0.0
        cover_days = r["stock"] / r["daily_mean"] if r["daily_mean"] > 0 else None
        urgency = ("urgent" if r["daily_mean"] > 0 and cover_days is not None and cover_days <= max(L, 1)
                   else "high" if r["stock"] < r["demand"] else "normal" if qty > 0 else "none")
        parts = [f"Forecast {r['demand']:.1f} {it.get('unit', 'units')} over {L}d lead + {max(1, int(review_period_days))}d review",
                 f"safety stock {r['safety']:.1f}", f"on hand {r['stock']:g}"]
        if r["raw"] > r["max_shelf"] + 1e-6:
            parts.append(f"capped to {r['max_shelf']:.1f} sellable within {r['shelf']}d shelf life")
        if cap_scale < 1:
            parts.append(f"scaled to {cap_scale:.0%} to fit free storage")
        out.append({"product_id": it.get("product_id"), "current_stock": round(r["stock"], 2),
                    "forecast_demand": round(r["demand"], 2), "safety_stock": round(r["safety"], 2),
                    "recommended_qty": round(qty, 1), "max_by_shelf_life": round(r["max_shelf"], 1),
                    "max_by_capacity": round(max_cap, 1) if max_cap is not None else None,
                    "naive_order_qty": round(r["naive"], 1), "expected_waste_avoided": round(waste_avoided, 1),
                    "days_of_cover": round(cover_days, 1) if cover_days is not None else None,
                    "urgency": urgency, "rationale": "; ".join(parts) + ".", "model": r["model"]})
    return out, {"capacity_scale": round(cap_scale, 3), "free_storage": free}
