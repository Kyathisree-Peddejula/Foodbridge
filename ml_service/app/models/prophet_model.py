"""Prophet demand model per first-level product category (with exogenous regressors)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
REGRESSORS = ["discount", "holiday_flag", "activity_flag", "avg_temperature", "precpt"]


def category_frame(daily: pd.DataFrame, cat: int) -> pd.DataFrame:
    g = daily[daily["first_category_id"] == cat]
    agg = g.groupby("dt").agg(y=("demand", "mean"), discount=("discount", "mean"),
                              holiday_flag=("holiday_flag", "max"), activity_flag=("activity_flag", "mean"),
                              avg_temperature=("avg_temperature", "mean"), precpt=("precpt", "mean")).reset_index()
    return agg.rename(columns={"dt": "ds"})


class CategoryProphet:
    def __init__(self):
        self.models: dict[int, object] = {}
        self.future_defaults: dict[int, dict] = {}
        self.last_date: dict[int, str] = {}

    def fit(self, daily: pd.DataFrame, categories=None):
        from prophet import Prophet
        cats = categories or sorted(daily["first_category_id"].unique())
        for cat in cats:
            df = category_frame(daily, int(cat))
            if len(df) < 21:
                continue
            m = Prophet(weekly_seasonality=True, yearly_seasonality=False, daily_seasonality=False,
                        interval_width=0.8, changepoint_prior_scale=0.05)
            for r in REGRESSORS:
                m.add_regressor(r, standardize=True)
            m.fit(df)
            self.models[int(cat)] = m
            tail = df.tail(14)
            self.future_defaults[int(cat)] = {"discount": float(tail["discount"].mean()), "holiday_flag": 0.0,
                                              "activity_flag": float(tail["activity_flag"].mean()),
                                              "avg_temperature": float(tail["avg_temperature"].mean()),
                                              "precpt": float(tail["precpt"].mean())}
            self.last_date[int(cat)] = str(df["ds"].max().date())
        log.info("Prophet fitted for %d categories", len(self.models))
        return self

    def predict(self, cat: int, horizon: int, start: pd.Timestamp | None = None, exog: dict | None = None):
        """Returns (yhat, lower, upper) arrays for `horizon` days after the training end (or `start`)."""
        m = self.models.get(int(cat))
        if m is None:
            return None
        start = start or (pd.Timestamp(self.last_date[int(cat)]) + pd.Timedelta(days=1))
        fut = pd.DataFrame({"ds": pd.date_range(start, periods=horizon, freq="D")})
        for k, v in {**self.future_defaults[int(cat)], **(exog or {})}.items():
            fut[k] = v
        fc = m.predict(fut)
        clip = lambda a: np.clip(a.values, 0, None)  # noqa: E731
        return clip(fc["yhat"]), clip(fc["yhat_lower"]), clip(fc["yhat_upper"])

    def weekly_shape(self, cat: int, horizon: int, start: pd.Timestamp):
        r = self.predict(cat, horizon, start)
        if r is None:
            return None
        y = r[0]
        return y / y.mean() if y.mean() > 0 else np.ones(horizon)

    # --- persistence
    def save(self, directory: Path):
        from prophet.serialize import model_to_json
        directory.mkdir(parents=True, exist_ok=True)
        for cat, m in self.models.items():
            (directory / f"cat_{cat}.json").write_text(model_to_json(m))
        (directory / "meta.json").write_text(json.dumps({"future_defaults": self.future_defaults,
                                                         "last_date": self.last_date}))

    @classmethod
    def load(cls, directory: Path):
        from prophet.serialize import model_from_json
        obj = cls()
        meta_p = directory / "meta.json"
        if not meta_p.exists():
            return None
        meta = json.loads(meta_p.read_text())
        obj.future_defaults = {int(k): v for k, v in meta["future_defaults"].items()}
        obj.last_date = {int(k): v for k, v in meta["last_date"].items()}
        for p in directory.glob("cat_*.json"):
            obj.models[int(p.stem.split("_")[1])] = model_from_json(p.read_text())
        return obj
