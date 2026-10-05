"""
Global LSTM demand forecaster (PyTorch).

One model is trained across many (store, product) series. Each sample is a 28-day window of
features -> the next H days of demand, both scaled by the window's mean demand so that series
of very different volumes share one model. A learned category embedding lets the network adapt
to category-specific dynamics. Output is a direct multi-horizon forecast (no error accumulation).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)
FEATS = ["demand", "discount", "holiday_flag", "activity_flag", "avg_temperature", "precpt"]


def _torch():
    import torch
    import torch.nn as nn
    return torch, nn


def build_net(n_features, n_categories, horizon, hidden=64, emb=8):
    torch, nn = _torch()

    class DemandLSTM(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb = nn.Embedding(n_categories + 1, emb)
            self.lstm = nn.LSTM(n_features, hidden, num_layers=2, batch_first=True, dropout=0.1)
            self.head = nn.Sequential(nn.Linear(hidden + emb, hidden), nn.ReLU(), nn.Linear(hidden, horizon))

        def forward(self, x, cat):
            out, _ = self.lstm(x)
            z = torch.cat([out[:, -1, :], self.emb(cat)], dim=1)
            return torch.nn.functional.softplus(self.head(z))  # demand >= 0

    return DemandLSTM()


class GlobalLSTM:
    def __init__(self, window=28, horizon=14):
        self.window, self.horizon = window, horizon
        self.cat_index: dict[int, int] = {}
        self.norm: dict[str, list[float]] = {}
        self.net = None
        self.history: list[dict] = []

    # ---- feature engineering
    def _matrix(self, g: pd.DataFrame) -> np.ndarray:
        """(T, F) matrix for one series; demand scaled later per window."""
        cols = []
        for f in FEATS:
            v = g[f].to_numpy(float) if f in g else np.zeros(len(g))
            if f in ("avg_temperature", "precpt"):
                mu, sd = self.norm.get(f, (0.0, 1.0))
                v = (v - mu) / (sd or 1.0)
            cols.append(v)
        dow = pd.to_datetime(g["dt"]).dt.dayofweek.to_numpy() if "dt" in g else np.arange(len(g)) % 7
        cols += [np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7)]
        return np.stack(cols, axis=1).astype(np.float32)

    def _windows(self, daily: pd.DataFrame, series_ids, stride=2, end_offset=0):
        X, C, Y = [], [], []
        L, H = self.window, self.horizon
        for sid, g in daily[daily["series"].isin(series_ids)].groupby("series"):
            m = self._matrix(g)
            cat = self.cat_index.get(int(g["first_category_id"].iloc[0]), 0)
            T = len(m) - end_offset
            for s in range(0, T - L - H + 1, stride):
                x = m[s:s + L].copy()
                scale = x[:, 0].mean() + 1e-3
                x[:, 0] /= scale
                X.append(x)
                Y.append(m[s + L:s + L + H, 0] / scale)
                C.append(cat)
        return np.array(X, np.float32), np.array(C, np.int64), np.array(Y, np.float32)

    # ---- training
    def fit(self, daily: pd.DataFrame, max_series=3000, epochs=8, batch=256, lr=2e-3, seed=0, holdout=0):
        torch, nn = _torch()
        torch.manual_seed(seed)
        rng = np.random.default_rng(seed)
        self.cat_index = {int(c): i + 1 for i, c in enumerate(sorted(daily["first_category_id"].unique()))}
        for f in ("avg_temperature", "precpt"):
            self.norm[f] = [float(daily[f].mean()), float(daily[f].std() or 1.0)]
        # keep series with enough non-zero history
        counts = daily.groupby("series")["demand"].agg(["size", lambda s: (s > 0).mean()])
        counts.columns = ["n", "nz"]
        ok = counts[(counts["n"] >= self.window + self.horizon) & (counts["nz"] > 0.2)].index.to_numpy()
        chosen = rng.choice(ok, size=min(max_series, len(ok)), replace=False) if len(ok) else ok
        X, C, Y = self._windows(daily, set(chosen), end_offset=holdout)
        if len(X) == 0:
            raise ValueError("Not enough history to train the LSTM")
        log.info("LSTM training on %d windows from %d series", len(X), len(chosen))
        self.net = build_net(X.shape[2], len(self.cat_index), self.horizon)
        opt = torch.optim.Adam(self.net.parameters(), lr=lr)
        loss_fn = nn.HuberLoss(delta=1.0)
        idx = np.arange(len(X))
        n_val = max(1, int(0.1 * len(X)))
        rng.shuffle(idx)
        val, tr = idx[:n_val], idx[n_val:]
        Xt, Ct, Yt = map(torch.from_numpy, (X, C, Y))
        self.history = []
        for ep in range(epochs):
            self.net.train()
            rng.shuffle(tr)
            tot = 0.0
            for i in range(0, len(tr), batch):
                b = tr[i:i + batch]
                opt.zero_grad()
                loss = loss_fn(self.net(Xt[b], Ct[b]), Yt[b])
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.net.parameters(), 1.0)
                opt.step()
                tot += loss.item() * len(b)
            self.net.eval()
            with torch.no_grad():
                vl = loss_fn(self.net(Xt[val], Ct[val]), Yt[val]).item()
            self.history.append({"epoch": ep + 1, "train_loss": round(tot / max(len(tr), 1), 4),
                                 "val_loss": round(vl, 4)})
            log.info("LSTM epoch %d train %.4f val %.4f", ep + 1, tot / max(len(tr), 1), vl)
        self.trained_series = int(len(chosen))
        self.trained_windows = int(len(X))
        return self

    # ---- inference
    def predict_history(self, hist: pd.DataFrame, first_category_id: int | None):
        """hist: last `window` days with FEATS (+dt). Returns H-day forecast in demand units."""
        torch, _ = _torch()
        if self.net is None or len(hist) < self.window:
            return None
        m = self._matrix(hist.tail(self.window))
        scale = m[:, 0].mean() + 1e-3
        m[:, 0] /= scale
        cat = self.cat_index.get(int(first_category_id), 0) if first_category_id is not None else 0
        with torch.no_grad():
            y = self.net(torch.from_numpy(m[None]), torch.tensor([cat])).numpy()[0]
        return np.clip(y * scale, 0, None)

    def predict_many(self, daily: pd.DataFrame, series_ids, end_date):
        """Batch forecast from the `window` days ending at end_date (inclusive)."""
        torch, _ = _torch()
        X, C, keys = [], [], []
        sub = daily[(daily["series"].isin(series_ids)) & (daily["dt"] <= end_date)]
        for sid, g in sub.groupby("series"):
            g = g.tail(self.window)
            if len(g) < self.window:
                continue
            m = self._matrix(g)
            s = m[:, 0].mean() + 1e-3
            m[:, 0] /= s
            X.append(m)
            C.append(self.cat_index.get(int(g["first_category_id"].iloc[0]), 0))
            keys.append((sid, s))
        if not X:
            return {}
        with torch.no_grad():
            Y = self.net(torch.from_numpy(np.array(X, np.float32)), torch.tensor(C)).numpy()
        return {sid: np.clip(Y[i] * s, 0, None) for i, (sid, s) in enumerate(keys)}

    # ---- persistence
    def save(self, directory: Path):
        torch, _ = _torch()
        directory.mkdir(parents=True, exist_ok=True)
        torch.save(self.net.state_dict(), directory / "lstm.pt")
        (directory / "lstm_meta.json").write_text(json.dumps({
            "window": self.window, "horizon": self.horizon, "cat_index": self.cat_index, "norm": self.norm,
            "n_features": len(FEATS) + 2, "history": self.history,
            "trained_series": getattr(self, "trained_series", None),
            "trained_windows": getattr(self, "trained_windows", None)}))

    @classmethod
    def load(cls, directory: Path):
        torch, _ = _torch()
        meta_p = directory / "lstm_meta.json"
        if not meta_p.exists():
            return None
        meta = json.loads(meta_p.read_text())
        obj = cls(meta["window"], meta["horizon"])
        obj.cat_index = {int(k): v for k, v in meta["cat_index"].items()}
        obj.norm = meta["norm"]
        obj.history = meta.get("history", [])
        obj.trained_series = meta.get("trained_series")
        obj.net = build_net(meta["n_features"], len(obj.cat_index), obj.horizon)
        obj.net.load_state_dict(torch.load(directory / "lstm.pt", map_location="cpu"))
        obj.net.eval()
        return obj
