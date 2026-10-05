"""
AI matching engine: ranks NGOs for a surplus listing.

Signals (each 0..1):
  category   - listing category vs NGO requirement categories
  proximity  - haversine distance, decays faster for highly perishable / urgent food
  quantity   - fit between listing quantity and NGO min/max + daily capacity
  semantic   - TF-IDF cosine similarity between listing text and the NGO's needs text
  history    - learned preference: share of the NGO's past completed pickups in this category
  reliability- NGO pickup reliability (Bayesian estimate from completed vs no-show)
  timing     - overlap between listing availability windows and NGO pickup days/hours
Hard constraints: distance limit, dietary restrictions, refrigeration for cold-chain food.
Weights adapt to urgency: food expiring today favours proximity & reliability.
"""
import math
from datetime import date

from django.db.models import Count, Q

from accounts.models import Organization
from core.geo import haversine_km
from django.utils import timezone

BASE_WEIGHTS = {"category": 0.24, "proximity": 0.22, "quantity": 0.15, "semantic": 0.10,
                "history": 0.10, "reliability": 0.12, "timing": 0.07}


def _tfidf_similarity(doc, others):
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:  # pragma: no cover - simple token overlap fallback
        a = set(doc.lower().split())
        return [len(a & set(o.lower().split())) / (len(a | set(o.lower().split())) or 1) for o in others]
    if not any(o.strip() for o in others):
        return [0.0] * len(others)
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    m = vec.fit_transform([doc] + others)
    return cosine_similarity(m[0:1], m[1:]).ravel().tolist()


def _timing(listing, req):
    windows = list(listing.windows.all())
    if not req or not windows:
        return 0.6
    days = set(req.pickup_days or range(7))
    ok = 0
    for w in windows:
        s, e = w.start.astimezone(), w.end.astimezone()
        if s.weekday() in days or e.weekday() in days:
            if s.hour < req.pickup_to_hour and e.hour >= req.pickup_from_hour:
                ok += 1
    return ok / len(windows)


def rank_ngos(listing, limit=10, only_ngo=None):
    ngos = Organization.objects.filter(org_type="ngo").prefetch_related("requirements__categories")
    if only_ngo:
        ngos = ngos.filter(pk=only_ngo.pk)
    ngos = list(ngos)
    if not ngos:
        return []

    days_left = (listing.expiry_date - timezone.localdate()).days
    perish = listing.category.perishability if listing.category else "medium"
    urgent = days_left <= 1 or perish == "high"
    w = dict(BASE_WEIGHTS)
    if urgent:
        w["proximity"] += 0.08
        w["reliability"] += 0.04
        w["semantic"] -= 0.05
        w["history"] -= 0.04
        w["timing"] -= 0.03

    # learned category preference from pickup history
    from marketplace.models import Pickup
    totals = dict(Pickup.objects.filter(status="completed").values_list("ngo").annotate(n=Count("id")))
    in_cat = dict(Pickup.objects.filter(status="completed", listing__category=listing.category)
                  .values_list("ngo").annotate(n=Count("id"))) if listing.category else {}

    listing_text = " ".join(filter(None, [listing.title, listing.description,
                                          listing.category.name if listing.category else ""]))
    need_texts = []
    for n in ngos:
        reqs = [r for r in n.requirements.all() if r.is_active]
        need_texts.append(" ".join([r.title + " " + r.notes + " " +
                                    " ".join(c.name for c in r.categories.all()) for r in reqs]))
    sims = _tfidf_similarity(listing_text, need_texts)

    results = []
    remaining = listing.remaining_kg
    for n, sim in zip(ngos, sims):
        reqs = [r for r in n.requirements.all() if r.is_active]
        best = None
        for req in reqs or [None]:
            reasons, excluded = [], None
            dist = haversine_km(listing.latitude, listing.longitude, n.latitude, n.longitude)
            max_d = req.max_distance_km if req else 20.0
            if dist is not None and dist > max_d:
                excluded = f"{dist:.1f} km is beyond the {max_d:g} km range"
            if req and req.dietary_restrictions:
                allowed = set(req.dietary_restrictions)
                if listing.dietary_tags and not (set(listing.dietary_tags) & allowed):
                    excluded = "dietary restrictions do not match"
                if "veg" in allowed and "non_veg" in listing.dietary_tags:
                    excluded = "NGO accepts vegetarian food only"
            if listing.requires_refrigeration and req is not None and not req.has_refrigeration:
                excluded = "needs cold storage the NGO does not have"
            if excluded:
                continue

            cat_ids = {c.id for c in req.categories.all()} if req else set()
            if not cat_ids:
                category = 0.55
            elif listing.category_id in cat_ids:
                category = 1.0
                reasons.append(f"Needs {listing.category.name.lower()}")
            else:
                category = 0.15
            if dist is None:
                proximity = 0.5
            else:
                scale = max_d / (3.0 if urgent else 2.0)
                proximity = math.exp(-dist / max(scale, 0.5))
                reasons.append(f"{dist:.1f} km away")
            cap = min(req.max_quantity_kg if req else n.daily_capacity_kg, n.daily_capacity_kg or 1e9)
            lo = req.min_quantity_kg if req else 0
            if remaining < lo:
                quantity = 0.3 * remaining / lo if lo else 0.3
            else:
                quantity = min(remaining, cap) / max(remaining, cap) if cap else 0.3
            if quantity > 0.7:
                reasons.append("Quantity fits capacity")
            tot = totals.get(n.id, 0)
            history = (in_cat.get(n.id, 0) + 1) / (tot + 3)
            reliability = n.reliability_score
            timing = _timing(listing, req)
            if timing >= 0.99 and req:
                reasons.append("Pickup times align")
            parts = {"category": category, "proximity": proximity, "quantity": quantity, "semantic": sim,
                     "history": history, "reliability": reliability, "timing": timing}
            score = 100 * sum(w[k] * v for k, v in parts.items())
            cand = {"ngo": n, "requirement": req, "score": round(score, 1),
                    "distance_km": round(dist, 2) if dist is not None else None,
                    "breakdown": {k: round(v, 3) for k, v in parts.items()},
                    "weights": {k: round(v, 3) for k, v in w.items()}, "reasons": reasons[:4]}
            if best is None or cand["score"] > best["score"]:
                best = cand
        if best:
            results.append(best)
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def update_reliability(ngo):
    from marketplace.models import Pickup
    stats = Pickup.objects.filter(ngo=ngo).aggregate(
        done=Count("id", filter=Q(status="completed")), bad=Count("id", filter=Q(status="no_show")))
    ngo.reliability_score = round((stats["done"] + 4) / (stats["done"] + stats["bad"] + 5), 3)
    ngo.save(update_fields=["reliability_score"])
