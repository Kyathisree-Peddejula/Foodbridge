"""Scheduled batch prediction runs: pull inventory snapshot from Django, score, push results back."""
from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.risk import score_items

log = logging.getLogger(__name__)
RUNS: deque = deque(maxlen=50)
_scheduler: BackgroundScheduler | None = None


def run_batch(trigger: str = "manual") -> dict:
    t0 = time.time()
    rec = {"started_at": datetime.utcnow().isoformat(), "trigger": trigger, "status": "running"}
    headers = {"X-Service-Key": settings.service_key}
    try:
        with httpx.Client(timeout=120) as c:
            snap = c.get(f"{settings.django_url}/internal/inventory-snapshot/", headers=headers)
            snap.raise_for_status()
            data = snap.json()
            results = score_items(data["items"])
            r = c.post(f"{settings.django_url}/internal/risk-scores/", params={"run_id": data.get("run_id")},
                       json={"results": results}, headers=headers)
            r.raise_for_status()
        levels = {}
        for x in results:
            levels[x["risk_level"]] = levels.get(x["risk_level"], 0) + 1
        rec.update(status="done", run_id=data.get("run_id"), items_scored=len(results), levels=levels,
                   django_response=r.json())
    except Exception as exc:
        log.warning("batch run failed: %s", exc)
        rec.update(status="failed", error=str(exc)[:300])
    rec["seconds"] = round(time.time() - t0, 2)
    rec["finished_at"] = datetime.utcnow().isoformat()
    RUNS.appendleft(rec)
    return rec


def start():
    global _scheduler
    if _scheduler or not settings.enable_scheduler:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(run_batch, "interval", hours=settings.batch_every_hours, kwargs={"trigger": "scheduled"},
                       id="risk-batch", next_run_time=None, max_instances=1, coalesce=True)
    _scheduler.start()
    log.info("batch scheduler started (every %sh)", settings.batch_every_hours)


def next_run():
    if not _scheduler:
        return None
    job = _scheduler.get_job("risk-batch")
    return job.next_run_time.isoformat() if job and job.next_run_time else None


def stop():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
