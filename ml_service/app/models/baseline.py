import numpy as np


def seasonal_naive(history, horizon):
    """Average of the same weekday over the last 4 weeks (robust baseline)."""
    h = np.asarray(history, float)
    if len(h) == 0:
        return np.zeros(horizon)
    if len(h) < 7:
        return np.full(horizon, h.mean())
    out = []
    for i in range(horizon):
        idx = [len(h) - 7 * k + (i % 7) for k in range(1, 5)]
        vals = [h[j] for j in idx if 0 <= j < len(h)]
        out.append(np.mean(vals) if vals else h[-7:].mean())
    return np.asarray(out)
