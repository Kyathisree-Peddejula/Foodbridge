"""Training, evaluation and inference orchestration for the demand forecasting models."""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, datetime

import numpy as np
import pandas as pd

from app.config import FRESH_SLUGS, settings
from app.data import dataset_summary, prepare, series_stats
from app.models.baseline import seasonal_naive
from app.models.lstm_model import FEATS, GlobalLSTM
from app.models.prophet_model import CategoryProphet

log = logging.getLogger(__name__)
ART = settings.artifacts_dir


def metrics(actual: np.ndarray, pred: np.ndarray) -> dict:
    a, p = np.asarray(actual, float).ravel(), np.asarray(pred, float).ravel()
    err = p - a
    denom = np.abs(a).sum()
    smape = np.mean(np.where((np.abs(a) + np.abs(p)) > 0, 2 * np.abs(err) / (np.abs(a) + np.abs(p) + 1e-9), 0))
    return {"mae": round(float(np.abs(err).mean()), 4), "rmse": round(float(np.sqrt((err ** 2).mean())), 4),
            "wape": round(float(np.abs(err).sum() / denom), 4) if denom else None,
            "smape": round(float(smape), 4), "bias": round(float(err.sum() / denom), 4) if denom else None}


class ForecastService:
    def __init__(self):
        self.prophet: CategoryProphet | None = None
        self.lstm: GlobalLSTM | None = None
        self.stats: pd.DataFrame | None = None
        self.tails: dict[str, pd.DataFrame] = {}
        self.cat_means: dict[int, float] = {}
        self.shapes: dict[int, tuple[np.ndarray, int]] = {}  # cat -> (21-day shape, weekday of day 0)
        self.report: dict = {}
        self.weights = {"lstm": 0.5, "prophet": 0.5}
        self.status = {"state": "idle", "message": "", "started_at": None, "finished_at": None}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ persistence
    def load(self):
        try:
            self.prophet = CategoryProphet.load(ART / "prophet")
        except Exception:
            log.exception("could not load prophet artifacts")
        try:
            self.lstm = GlobalLSTM.load(ART / "lstm")
        except Exception:
            log.exception("could not load lstm artifacts")
        if (ART / "series_stats.parquet").exists():
            self.stats = pd.read_parquet(ART / "series_stats.parquet").set_index("series")
            self.cat_means = self.stats.groupby("first_category_id")["cat_mean28"].first().to_dict()
        if (ART / "series_tail.parquet").exists():
            t = pd.read_parquet(ART / "series_tail.parquet")
            self.tails = {k: g for k, g in t.groupby("series")}
        if (ART / "metrics.json").exists():
            self.report = json.loads((ART / "metrics.json").read_text())
            self.weights = self.report.get("ensemble_weights", self.weights)
        self._cache_shapes()
        log.info("models loaded: prophet=%s lstm=%s series=%s", bool(self.prophet), bool(self.lstm),
                 0 if self.stats is None else len(self.stats))

    def _cache_shapes(self):
        self.shapes = {}
        if not self.prophet:
            return
        for cat in self.prophet.models:
            if cat not in self.prophet.last_date:
                continue
            start = pd.Timestamp(self.prophet.last_date[cat]) + pd.Timedelta(days=1)
            shape = self.prophet.weekly_shape(cat, 21, start)
            self.shapes[cat] = (shape, start.dayofweek)

    @property
    def ready(self):
        return self.prophet is not None or self.lstm is not None

    # ------------------------------------------------------------------ training
    def train_async(self, **kw):
        if self.status["state"] == "training":
            return False
        threading.Thread(target=self.train, kwargs=kw, daemon=True).start()
        return True

    def train(self, models=("prophet", "lstm"), max_series=None, epochs=None, eval_series=None):
        with self._lock:
            t0 = time.time()
            self.status = {"state": "training", "message": "loading dataset",
                           "started_at": datetime.utcnow().isoformat(), "finished_at": None}
            try:
                train_daily, profiles = prepare("train")
                eval_path = settings.dataset_dir / "eval.parquet"
                if eval_path.exists():
                    eval_daily, _ = prepare("eval", eval_path, profiles)
                    fit_daily, mode = train_daily, "official eval split (next 7 days)"
                else:
                    cut = train_daily["dt"].max() - pd.Timedelta(days=7)
                    fit_daily, eval_daily = train_daily[train_daily["dt"] <= cut], train_daily[train_daily["dt"] > cut]
                    mode = "last 7 days of train held out"
                self.status["message"] = "fitting models"
                prophet = CategoryProphet().fit(fit_daily) if "prophet" in models else None
                lstm = None
                if "lstm" in models:
                    lstm = GlobalLSTM(settings.lstm_window, settings.horizon).fit(
                        fit_daily, max_series=max_series or settings.lstm_max_series,
                        epochs=epochs or settings.lstm_epochs)
                self.status["message"] = "evaluating"
                report = self.evaluate(fit_daily, eval_daily, prophet, lstm, eval_series or settings.eval_series)
                report.update({"evaluation_mode": mode, "dataset": dataset_summary(train_daily),
                               "trained_at": datetime.utcnow().isoformat(),
                               "train_seconds": round(time.time() - t0, 1),
                               "lstm_training_curve": lstm.history if lstm else [],
                               "lstm_trained_series": getattr(lstm, "trained_series", None),
                               "stockout_adjusted_rows": int(train_daily["demand"].ne(train_daily["sale_amount"]).sum())})
                if eval_path.exists():
                    full = train_daily
                else:  # refit on all data for production after honest evaluation
                    self.status["message"] = "refitting on full history"
                    full = train_daily
                    prophet = CategoryProphet().fit(full) if prophet else None
                    if lstm:
                        lstm = GlobalLSTM(settings.lstm_window, settings.horizon).fit(
                            full, max_series=max_series or settings.lstm_max_series,
                            epochs=epochs or settings.lstm_epochs)
                if prophet:
                    prophet.save(ART / "prophet")
                if lstm:
                    lstm.save(ART / "lstm")
                series_stats(full).to_parquet(ART / "series_stats.parquet", index=False)
                end = full["dt"].max()
                full[full["dt"] > end - pd.Timedelta(days=settings.lstm_window)][["series", "dt", "first_category_id", *FEATS]] \
                    .to_parquet(ART / "series_tail.parquet", index=False)
                (ART / "metrics.json").write_text(json.dumps(report, indent=2, default=str))
                self.load()
                self.status.update(state="done", message="training complete",
                                   finished_at=datetime.utcnow().isoformat())
                return report
            except Exception as exc:
                log.exception("training failed")
                self.status.update(state="failed", message=str(exc), finished_at=datetime.utcnow().isoformat())
                raise

    def evaluate(self, fit_daily, eval_daily, prophet, lstm, n_series):
        H = int(eval_daily["dt"].nunique())
        common = np.intersect1d(fit_daily["series"].unique(), eval_daily["series"].unique())
        rng = np.random.default_rng(1)
        sample = rng.choice(common, size=min(n_series, len(common)), replace=False)
        stats = series_stats(fit_daily).set_index("series")
        start = eval_daily["dt"].min()
        fit_end = fit_daily["dt"].max()
        lstm_preds = lstm.predict_many(fit_daily, set(sample), fit_end) if lstm else {}
        cat_fc = {}
        preds = {k: [] for k in ["seasonal_naive", "prophet", "lstm", "ensemble"]}
        actuals, cats = [], []
        hist_groups = {k: g for k, g in fit_daily[fit_daily["series"].isin(sample)].groupby("series")}
        eval_groups = {k: g for k, g in eval_daily[eval_daily["series"].isin(sample)].groupby("series")}
        for sid in sample:
            act = eval_groups[sid].sort_values("dt")["demand"].to_numpy()[:H]
            if len(act) < H:
                continue
            hist = hist_groups[sid]["demand"].to_numpy()
            cat = int(hist_groups[sid]["first_category_id"].iloc[0])
            naive = seasonal_naive(hist, H)
            p = None
            if prophet:
                if cat not in cat_fc:
                    cat_fc[cat] = prophet.predict(cat, H, start)
                if cat_fc[cat] is not None:
                    p = cat_fc[cat][0] * float(stats.loc[sid, "ratio"])
            l = lstm_preds.get(sid)
            l = l[:H] if l is not None else None
            p = p if p is not None else naive
            l = l if l is not None else naive
            preds["seasonal_naive"].append(naive)
            preds["prophet"].append(p)
            preds["lstm"].append(l)
            preds["ensemble"].append(0.5 * p + 0.5 * l)
            actuals.append(act)
            cats.append(cat)
        A = np.array(actuals)
        results = {k: metrics(A, np.array(v)) for k, v in preds.items() if v and (k != "prophet" or prophet)
                   and (k != "lstm" or lstm)}
        # per-category WAPE (useful to see where each model wins)
        per_cat = []
        C = np.array(cats)
        for c in sorted(set(cats)):
            mk = C == c
            row = {"first_category_id": int(c), "taxonomy": FRESH_SLUGS[c % len(FRESH_SLUGS)], "series": int(mk.sum())}
            for k in results:
                row[k] = metrics(A[mk], np.array(preds[k])[mk])["wape"]
            per_cat.append(row)
        w = {}
        for k in ("prophet", "lstm"):
            if k in results and results[k]["wape"]:
                w[k] = 1 / results[k]["wape"]
        s = sum(w.values()) or 1
        weights = {k: round(v / s, 3) for k, v in w.items()} or {"lstm": 0.5, "prophet": 0.5}
        best = min(results, key=lambda k: results[k]["wape"] or 9e9)
        return {"horizon_days": H, "series_evaluated": int(len(A)), "metrics": results,
                "per_category_wape": per_cat, "best_model": best, "ensemble_weights": weights,
                "notes": ["Demand targets are stock-out corrected (latent demand).",
                          "Ensemble in the report is an equal-weight average; production uses inverse-WAPE weights."]}

    # ------------------------------------------------------------------ inference
    def _categories_for(self, item) -> list[int]:
        if item.get("fr_first_category_id") is not None:
            return [int(item["fr_first_category_id"])]
        slug = item.get("category_slug")
        if slug in FRESH_SLUGS and self.prophet:
            idx = FRESH_SLUGS.index(slug)
            return [c for c in self.prophet.models if c % len(FRESH_SLUGS) == idx]
        return []

    def _shape(self, cats, horizon, start: date):
        shapes = []
        for c in cats:
            if c in self.shapes:
                s, dow0 = self.shapes[c]
                offset = (start.weekday() - dow0) % 7
                shapes.append(np.resize(s[offset:offset + 14], horizon) if horizon > 0 else s[:0])
        if not shapes:
            return None
        m = np.mean(shapes, axis=0)
        return m / m.mean() if m.mean() > 0 else np.ones(horizon)

    def _history_frame(self, item, hist):
        key = f"{item.get('fr_store_id')}_{item.get('fr_product_id')}"
        tail = self.tails.get(key)
        n = len(hist)
        idx = pd.date_range(end=pd.Timestamp(date.today()) - pd.Timedelta(days=1), periods=n, freq="D")
        df = pd.DataFrame({"dt": idx, "demand": hist})
        if tail is not None and len(tail) >= n:  # reuse the series' observed covariate pattern
            t = tail.tail(n).reset_index(drop=True)
            for f in FEATS[1:]:
                df[f] = t[f].to_numpy()
        else:
            df["discount"], df["holiday_flag"], df["activity_flag"] = 1.0, 0.0, 0.0
            mu = self.lstm.norm if self.lstm else {}
            df["avg_temperature"] = mu.get("avg_temperature", [20, 1])[0]
            df["precpt"] = mu.get("precpt", [0, 1])[0]
        return df, key

    def forecast(self, item: dict, horizon: int) -> dict:
        horizon = max(1, int(horizon))
        hist = np.asarray(item.get("recent_daily_sales") or [], float)
        key = f"{item.get('fr_store_id')}_{item.get('fr_product_id')}"
        if (hist.size == 0 or hist.sum() == 0) and key in self.tails:
            hist = self.tails[key]["demand"].to_numpy()
        cats = self._categories_for(item)
        today = date.today()
        comps, used = {}, []
        level = float(hist[-14:].mean()) if hist.size and hist.sum() > 0 else None
        if level is None:
            prior = [self.cat_means.get(c) for c in cats if self.cat_means.get(c)]
            level = float(np.mean(prior)) if prior else 0.0
        shape = self._shape(cats, horizon, today)
        if shape is not None and level > 0:
            comps["prophet"] = level * shape
        if self.lstm and hist.size >= self.lstm.window and hist.sum() > 0:
            df, _ = self._history_frame(item, hist[-self.lstm.window:])
            cat = cats[0] if cats else None
            y = self.lstm.predict_history(df, cat)
            if y is not None:
                comps["lstm"] = np.resize(np.concatenate([y, y[-7:]]), horizon) if horizon > len(y) else y[:horizon]
        if not comps:
            base = seasonal_naive(hist, horizon) if hist.size else np.full(horizon, level)
            comps["seasonal_naive"] = base
        if len(comps) > 1:
            w = {k: self.weights.get(k, 0.5) for k in comps}
            s = sum(w.values())
            yhat = sum(comps[k] * w[k] / s for k in comps)
            model = "ensemble(" + "+".join(sorted(comps)) + ")"
            used = w
        else:
            (model, yhat), = comps.items()
            used = {model: 1.0}
        yhat = np.clip(np.asarray(yhat, float), 0, None)
        err = (self.report.get("metrics", {}).get("ensemble" if len(comps) > 1 else model, {}) or {}).get("wape") or 0.35
        band = 1.28 * err
        return {"model": model, "weights": used, "horizon_days": horizon,
                "start_date": today.isoformat(),
                "daily": [round(float(v), 3) for v in yhat],
                "lower": [round(float(max(0, v * (1 - band))), 3) for v in yhat],
                "upper": [round(float(v * (1 + band)), 3) for v in yhat],
                "weekly": [round(float(yhat[i:i + 7].sum()), 3) for i in range(0, horizon, 7)],
                "components": {k: [round(float(x), 3) for x in v] for k, v in comps.items()},
                "expected_error_wape": round(err, 3)}


service = ForecastService()
