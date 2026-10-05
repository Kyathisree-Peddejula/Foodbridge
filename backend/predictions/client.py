import logging

import requests
from django.conf import settings

log = logging.getLogger(__name__)


class MLServiceError(Exception):
    pass


def _post(path, payload, timeout=None):
    url = settings.ML_SERVICE_URL.rstrip("/") + path
    try:
        r = requests.post(url, json=payload, timeout=timeout or settings.ML_SERVICE_TIMEOUT,
                          headers={"X-Service-Key": settings.SERVICE_API_KEY})
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        log.warning("ML service call %s failed: %s", path, exc)
        raise MLServiceError(str(exc)) from exc


def _get(path, params=None):
    url = settings.ML_SERVICE_URL.rstrip("/") + path
    try:
        r = requests.get(url, params=params, timeout=settings.ML_SERVICE_TIMEOUT,
                         headers={"X-Service-Key": settings.SERVICE_API_KEY})
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        raise MLServiceError(str(exc)) from exc


def score_batch(items):
    return _post("/risk/score/batch", {"items": items})["results"]


def reorder(items, cfg):
    return _post("/reorder/recommend", {"items": items, **cfg})["results"]


def forecast(item, horizon):
    return _post("/forecast", {**item, "horizon_days": horizon})


def model_status():
    return _get("/models")
