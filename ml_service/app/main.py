"""FoodBridge Waste Prediction Service (FastAPI). Swagger UI at /docs, ReDoc at /redoc."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date, timedelta

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app import reorder, risk, scheduler
from app.config import FRESH_SLUGS, settings
from app.forecaster import service
from app.schemas import (ForecastRequest, ForecastResponse, ReorderRequest, ReorderResponse, RiskBatchRequest,
                         RiskBatchResponse, RiskItem, RiskResult, TrainRequest)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    service.load()
    scheduler.start()
    yield
    scheduler.stop()


TAGS = [
    {"name": "health", "description": "Liveness and model readiness"},
    {"name": "training", "description": "Train Prophet + LSTM on FreshRetailNet-50K and inspect evaluation metrics"},
    {"name": "forecast", "description": "Daily & weekly demand forecasts"},
    {"name": "risk", "description": "Real-time, on-demand waste risk scoring"},
    {"name": "reorder", "description": "Smart reorder recommendations"},
    {"name": "batch", "description": "Scheduled batch prediction runs against the Django inventory"},
]

app = FastAPI(title="FoodBridge Waste Prediction Service", version="1.0.0", lifespan=lifespan, openapi_tags=TAGS,
              description="Demand forecasting (Prophet + LSTM ensemble), waste-risk scoring and smart reorder "
                          "recommendations for the FoodBridge platform. Pass `X-Service-Key` when "
                          "`REQUIRE_SERVICE_KEY=true`.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def auth(x_service_key: str | None = Header(None)):
    if settings.require_service_key and x_service_key != settings.service_key:
        raise HTTPException(401, "invalid service key")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "models_ready": service.ready, "training": service.status["state"]}


@app.get("/models", tags=["training"], dependencies=[Depends(auth)])
def models():
    rep = service.report
    return {"ready": service.ready, "prophet": bool(service.prophet), "lstm": bool(service.lstm),
            "prophet_categories": len(service.prophet.models) if service.prophet else 0,
            "series_known": 0 if service.stats is None else int(len(service.stats)),
            "ensemble_weights": service.weights, "training_status": service.status,
            "trained_at": rep.get("trained_at"), "metrics": rep.get("metrics"), "best_model": rep.get("best_model"),
            "evaluation_mode": rep.get("evaluation_mode"), "horizon_days": rep.get("horizon_days"),
            "series_evaluated": rep.get("series_evaluated"), "per_category_wape": rep.get("per_category_wape"),
            "lstm_training_curve": rep.get("lstm_training_curve"), "dataset": rep.get("dataset"),
            "batch_scheduler": {"every_hours": settings.batch_every_hours, "next_run": scheduler.next_run()}}


@app.post("/train", tags=["training"], dependencies=[Depends(auth)], status_code=202)
def train(req: TrainRequest):
    if not (settings.dataset_dir / "train.parquet").exists():
        raise HTTPException(400, f"dataset not found in {settings.dataset_dir}; run scripts/fetch_dataset.py")
    started = service.train_async(models=tuple(req.models), max_series=req.max_series, epochs=req.epochs,
                                  eval_series=req.eval_series)
    return {"started": started, "status": service.status}


@app.get("/train/status", tags=["training"])
def train_status():
    return service.status


@app.get("/data/summary", tags=["training"])
def data_summary():
    return service.report.get("dataset") or {"detail": "train models first"}


@app.post("/forecast", tags=["forecast"], response_model=ForecastResponse, dependencies=[Depends(auth)])
def forecast(req: ForecastRequest):
    return service.forecast(req.model_dump(), req.horizon_days)


@app.get("/forecast/category/{first_category_id}", tags=["forecast"], dependencies=[Depends(auth)])
def category_forecast(first_category_id: int, horizon: int = Query(14, ge=1, le=60)):
    """Aggregate Prophet forecast for a FreshRetailNet first-level category (average series level)."""
    if not service.prophet or first_category_id not in service.prophet.models:
        raise HTTPException(404, "no Prophet model for this category")
    start = date.today()
    import pandas as pd
    res = service.prophet.predict(first_category_id, horizon, pd.Timestamp(start))
    if res is None:
        raise HTTPException(404, "no forecast")
    yhat, lo, hi = res
    return {"first_category_id": first_category_id, "taxonomy": FRESH_SLUGS[first_category_id % len(FRESH_SLUGS)],
            "dates": [(start + timedelta(days=i)).isoformat() for i in range(horizon)],
            "daily": [round(float(v), 3) for v in yhat], "lower": [round(float(v), 3) for v in lo],
            "upper": [round(float(v), 3) for v in hi],
            "weekly": [round(float(yhat[i:i + 7].sum()), 3) for i in range(0, horizon, 7)]}


@app.post("/risk/score", tags=["risk"], response_model=RiskResult, dependencies=[Depends(auth)])
def risk_score(item: RiskItem):
    return risk.score_one(item.model_dump())


@app.post("/risk/score/batch", tags=["risk"], response_model=RiskBatchResponse, dependencies=[Depends(auth)])
def risk_batch(req: RiskBatchRequest):
    results = risk.score_items([i.model_dump() for i in req.items])
    levels = {}
    for r in results:
        levels[r["risk_level"]] = levels.get(r["risk_level"], 0) + 1
    return {"results": results, "summary": {"items": len(results), "levels": levels,
                                            "expected_waste_total": round(sum(r["expected_waste_qty"] for r in results), 2)}}


@app.post("/reorder/recommend", tags=["reorder"], response_model=ReorderResponse, dependencies=[Depends(auth)])
def reorder_recommend(req: ReorderRequest):
    results, constraints = reorder.recommend([i.model_dump() for i in req.items], req.lead_time_days,
                                             req.review_period_days, req.storage_capacity, req.storage_used)
    return {"results": results, "constraints": constraints}


@app.post("/batch/run", tags=["batch"], dependencies=[Depends(auth)])
def batch_run():
    """Trigger a batch run now (same job the scheduler runs every BATCH_EVERY_HOURS)."""
    return scheduler.run_batch("manual")


@app.get("/batch/runs", tags=["batch"])
def batch_runs():
    return {"every_hours": settings.batch_every_hours, "next_run": scheduler.next_run(), "runs": list(scheduler.RUNS)}
