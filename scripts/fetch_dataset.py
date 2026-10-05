"""
Download the FreshRetailNet-50K dataset from Hugging Face and store it as parquet
files that both the Django backend and the FastAPI ML service read.

    python scripts/fetch_dataset.py                 # full dataset from Hugging Face
    python scripts/fetch_dataset.py --synthetic     # offline, schema-identical sample

Output:  data/freshretailnet/train.parquet , data/freshretailnet/eval.parquet

Dataset: https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K
Columns: city_id, store_id, management_group_id, first_category_id,
second_category_id, third_category_id, product_id, dt, sale_amount,
hours_sale (24 floats), stock_hour6_22_cnt, hours_stock_status (24 ints, 1 = out of stock),
discount, holiday_flag, activity_flag, precpt, avg_temperature, avg_humidity,
avg_wind_level
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "freshretailnet"
HF_NAME = "Dingdong-Inc/FreshRetailNet-50K"


def fetch_from_hf(out_dir: Path) -> None:
    try:
        from datasets import load_dataset
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("pip install datasets   (needed to download from Hugging Face)") from exc

    print(f"Downloading {HF_NAME} from Hugging Face ...")
    ds = load_dataset(HF_NAME)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split in ds.keys():
        df = ds[split].to_pandas()
        path = out_dir / f"{split}.parquet"
        df.to_parquet(path, index=False)
        print(f"  {split}: {len(df):,} rows -> {path}")


def generate_synthetic(n_stores: int = 12, n_products: int = 60, days: int = 90,
                       eval_days: int = 7, seed: int = 7) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Produce data with exactly the FreshRetailNet-50K schema for offline development."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2024-03-28")
    dates = pd.date_range(start, periods=days + eval_days, freq="D")

    products = []
    for pid in range(n_products):
        first = int(rng.integers(0, 16))
        products.append({
            "product_id": pid,
            "first_category_id": first,
            "second_category_id": first * 10 + int(rng.integers(0, 5)),
            "third_category_id": first * 100 + int(rng.integers(0, 20)),
            "management_group_id": first // 4,
            "base": float(rng.gamma(2.0, 0.6)),
        })
    stores = [{"store_id": s, "city_id": int(rng.integers(0, 18))} for s in range(n_stores)]

    hour_profile = np.array([0, 0, 0, 0, 0, 0, 2, 5, 7, 8, 7, 6, 7, 7, 6, 6, 7, 9, 11, 10, 7, 4, 1, 0], float)
    hour_profile /= hour_profile.sum()

    city_weather = {c: (rng.normal(18, 4), rng.uniform(0.5, 1.5)) for c in range(18)}
    holidays = {pd.Timestamp("2024-04-04"), pd.Timestamp("2024-04-05"), pd.Timestamp("2024-05-01"),
                pd.Timestamp("2024-05-02"), pd.Timestamp("2024-05-03"), pd.Timestamp("2024-06-10")}

    rows = []
    for st in stores:
        store_mult = rng.uniform(0.6, 1.6)
        chosen = rng.choice(n_products, size=max(5, int(n_products * 0.7)), replace=False)
        t_mean, p_mean = city_weather[st["city_id"]]
        for pid in chosen:
            p = products[pid]
            trend = rng.normal(0, 0.003)
            for i, d in enumerate(dates):
                dow = d.dayofweek
                holiday = int(d in holidays)
                activity = int(rng.random() < 0.12)
                discount = float(np.clip(rng.normal(0.95, 0.05) - 0.15 * activity, 0.5, 1.0))
                temp = float(t_mean + 6 * np.sin(i / 90 * np.pi) + rng.normal(0, 2))
                precpt = float(max(0, rng.gamma(0.6, p_mean * 3) - 1.0))
                lam = (p["base"] * store_mult * (1 + trend * i)
                       * (1.25 if dow >= 5 else 1.0) * (1.3 if holiday else 1.0)
                       * (1 + 0.8 * (1 - discount)) * (0.85 if precpt > 5 else 1.0))
                hourly_true = rng.poisson(lam * 10 * hour_profile) / 10.0
                stock_status = np.zeros(24, int)
                if rng.random() < 0.18:  # stock-out late in the day
                    cut = int(rng.integers(14, 22))
                    stock_status[cut:] = 1
                hours_sale = np.where(stock_status == 1, 0.0, hourly_true)
                rows.append({
                    "city_id": st["city_id"], "store_id": st["store_id"],
                    "management_group_id": p["management_group_id"],
                    "first_category_id": p["first_category_id"],
                    "second_category_id": p["second_category_id"],
                    "third_category_id": p["third_category_id"],
                    "product_id": pid, "dt": d.strftime("%Y-%m-%d"),
                    "sale_amount": round(float(hours_sale.sum()), 3),
                    "hours_sale": hours_sale.round(3).tolist(),
                    "stock_hour6_22_cnt": int(stock_status[6:22].sum()),
                    "hours_stock_status": stock_status.tolist(),
                    "discount": round(discount, 3), "holiday_flag": holiday,
                    "activity_flag": activity, "precpt": round(precpt, 2),
                    "avg_temperature": round(temp, 2),
                    "avg_humidity": round(float(rng.uniform(40, 90)), 2),
                    "avg_wind_level": round(float(rng.uniform(1, 4)), 2),
                })
    df = pd.DataFrame(rows)
    cutoff = dates[days].strftime("%Y-%m-%d")
    return df[df["dt"] < cutoff].reset_index(drop=True), df[df["dt"] >= cutoff].reset_index(drop=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--synthetic", action="store_true", help="generate an offline sample instead of downloading")
    ap.add_argument("--stores", type=int, default=12)
    ap.add_argument("--products", type=int, default=60)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    args = ap.parse_args()

    if args.synthetic:
        train, ev = generate_synthetic(args.stores, args.products)
        args.out.mkdir(parents=True, exist_ok=True)
        train.to_parquet(args.out / "train.parquet", index=False)
        ev.to_parquet(args.out / "eval.parquet", index=False)
        print(f"Synthetic FreshRetailNet sample: train={len(train):,} eval={len(ev):,} rows -> {args.out}")
    else:
        fetch_from_hf(args.out)


if __name__ == "__main__":
    main()
