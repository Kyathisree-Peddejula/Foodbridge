"""
Versioned read-cache for dashboards and feeds.

Each organization has a data-version number; any write that affects it (stock, transactions,
listings, pickups, matches, alerts, needs) bumps the version via signals, so cached dashboards are
invalidated immediately in the worker that handled the write. With the default per-process
LocMem cache other workers may serve a result up to DASHBOARD_CACHE_SECONDS old; set REDIS_URL
to share the cache (and the versions) across all workers.
"""
from django.conf import settings
from django.core.cache import cache

PLATFORM = "platform"


def _vkey(scope):
    return f"fb:v:{scope}"


def version(scope):
    return cache.get_or_set(_vkey(scope), 1, timeout=None)


def bump(*scopes):
    for s in {*scopes, PLATFORM}:
        if s is None:
            continue
        try:
            cache.incr(_vkey(s))
        except ValueError:
            cache.set(_vkey(s), 2, timeout=None)


def cached(name, scope, fn, *, extra="", depends_on_platform=False):
    """Return fn() cached under (name, scope, versions)."""
    ttl = getattr(settings, "DASHBOARD_CACHE_SECONDS", 30)
    if ttl <= 0:
        return fn()
    v = f"{version(scope)}.{version(PLATFORM) if depends_on_platform else 0}"
    key = f"fb:c:{name}:{scope}:{v}:{extra}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    val = fn()
    cache.set(key, val, ttl)
    return val
