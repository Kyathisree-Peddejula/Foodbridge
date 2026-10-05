"""Train Prophet + LSTM demand models on FreshRetailNet-50K and write artifacts + metrics.json.

    python scripts/train.py                      # full run (uses data/freshretailnet/*.parquet)
    python scripts/train.py --max-series 1500 --epochs 5   # quicker
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("cmdstanpy").setLevel(logging.WARNING)

from app.forecaster import service  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--models", nargs="+", default=["prophet", "lstm"])
p.add_argument("--max-series", type=int)
p.add_argument("--epochs", type=int)
p.add_argument("--eval-series", type=int)
a = p.parse_args()
rep = service.train(models=tuple(a.models), max_series=a.max_series, epochs=a.epochs, eval_series=a.eval_series)
print(json.dumps({k: rep[k] for k in ("evaluation_mode", "horizon_days", "series_evaluated", "metrics",
                                      "best_model", "ensemble_weights", "train_seconds")}, indent=2))
