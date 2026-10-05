"""
Loading + preprocessing of FreshRetailNet-50K into daily demand time series.

Key step: *censored-demand recovery*. FreshRetailNet records hourly stock status; on days with
stock-outs the observed sales understate true demand. We estimate latent demand as

    demand = sales / share_of_daily_demand_in_hours_when_in_stock

where the hourly demand profile is learned per first-level category from fully in-stock days.
Training on recovered demand keeps the forecaster from learning artificially low demand (which
would cause under-ordering) while the risk engine still compares stock against realistic sales.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from app.config import settings

log = logging.getLogger(__name__)

EXOG = ["discount", "holiday_flag", "activity_flag", "precpt", "avg_temperature"]


def load_split(split: str = "train", path: Path | None = None) -> pd.DataFrame:
    p = path or settings.dataset_dir / f"{split}.parquet"
    if p.exists():
        return pd.read_parquet(p)
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise FileNotFoundError(f"{p} missing; run scripts/fetch_dataset.py") from exc
    log.info("Downloading FreshRetailNet-50K %s split from Hugging Face", split)
    return load_dataset("Dingdong-Inc/FreshRetailNet-50K", split=split).to_pandas()


def _stack(col: pd.Series, dtype) -> np.ndarray:
    return np.stack([np.asarray(v, dtype=dtype) for v in col.values]) if len(col) else np.zeros((0, 24), dtype)


def hourly_profiles(df: pd.DataFrame) -> dict[int, np.ndarray]:
    full = df[df["stock_hour6_22_cnt"] == 0]
    profiles = {}
    for cat, g in full.groupby("first_category_id"):
        h = _stack(g["hours_sale"], np.float32).sum(axis=0)
        if h.sum() > 0:
            profiles[int(cat)] = h / h.sum()
    glob = _stack(full["hours_sale"].head(200_000), np.float32).sum(axis=0)
    profiles[-1] = glob / glob.sum() if glob.sum() > 0 else np.full(24, 1 / 24)
    return profiles


def recover_demand(df: pd.DataFrame, profiles: dict[int, np.ndarray] | None = None) -> pd.DataFrame:
    df = df.copy()
    profiles = profiles or hourly_profiles(df)
    df["demand"] = df["sale_amount"].astype(float)
    mask = df["stock_hour6_22_cnt"].values > 0
    if mask.any():
        sub = df.loc[mask]
        status = _stack(sub["hours_stock_status"], np.int8)  # 1 = out of stock
        prof = np.stack([profiles.get(int(c), profiles[-1]) for c in sub["first_category_id"].values])
        in_stock_share = (prof * (status == 0)).sum(axis=1)
        factor = 1.0 / np.clip(in_stock_share, 0.35, 1.0)
        df.loc[mask, "demand"] = sub["sale_amount"].values * factor
    df["stockout_adjusted"] = mask
    return df


def to_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Canonical daily frame, one row per (series, day)."""
    out = df[["store_id", "product_id", "first_category_id", "dt", "sale_amount", "demand", *EXOG]].copy()
    out["dt"] = pd.to_datetime(out["dt"])
    out["series"] = out["store_id"].astype(str) + "_" + out["product_id"].astype(str)
    return out.sort_values(["series", "dt"]).reset_index(drop=True)


def prepare(split: str = "train", path: Path | None = None, profiles=None) -> tuple[pd.DataFrame, dict]:
    raw = load_split(split, path)
    profiles = profiles or hourly_profiles(raw)
    daily = to_daily(recover_demand(raw, profiles))
    return daily, profiles


def series_stats(daily: pd.DataFrame, last_days: int = 28) -> pd.DataFrame:
    end = daily["dt"].max()
    recent = daily[daily["dt"] > end - pd.Timedelta(days=last_days)]
    st = recent.groupby(["series", "store_id", "product_id", "first_category_id"]).agg(
        mean28=("demand", "mean"), std28=("demand", "std")).reset_index()
    cat_mean = recent.groupby("first_category_id")["demand"].mean().rename("cat_mean28")
    st = st.merge(cat_mean, on="first_category_id", how="left")
    st["ratio"] = (st["mean28"] / st["cat_mean28"].replace(0, np.nan)).fillna(1.0)
    return st


def dataset_summary(daily: pd.DataFrame) -> dict:
    return {
        "rows": int(len(daily)), "series": int(daily["series"].nunique()),
        "stores": int(daily["store_id"].nunique()), "products": int(daily["product_id"].nunique()),
        "categories": int(daily["first_category_id"].nunique()),
        "start": str(daily["dt"].min().date()), "end": str(daily["dt"].max().date()),
        "stockout_adjusted_share": None,
        "mean_daily_demand": round(float(daily["demand"].mean()), 4),
    }
