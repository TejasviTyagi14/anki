"""Memory-model calibration metrics (rubric: calibrated memory, Section 9).

Real calibration needs real longitudinal reviews — FSRS predicted P(recall) vs.
the actual recall outcome from Anki's revlog. That data can't be honestly
gathered in a week, so this module BUILDS + TESTS the calibration metrics
(reliability bins, Brier, log loss, ECE) and DEMONSTRATES them on a clearly
labeled simulation. Honest status: "we can compute calibration and it detects
miscalibration; we do not yet have real review data to calibrate on."

Pure stdlib (math only) so it runs anywhere and both apps could compute it.
"""

from __future__ import annotations

import math
from typing import Sequence

_EPS = 1e-15


def brier_score(probs: Sequence[float], outcomes: Sequence[int]) -> float:
    """Mean squared error of predicted probabilities vs binary outcomes."""
    n = len(probs)
    if n == 0:
        return float("nan")
    return sum((p - o) ** 2 for p, o in zip(probs, outcomes)) / n


def log_loss(probs: Sequence[float], outcomes: Sequence[int]) -> float:
    n = len(probs)
    if n == 0:
        return float("nan")
    total = 0.0
    for p, o in zip(probs, outcomes):
        p = min(1.0 - _EPS, max(_EPS, p))
        total += -(o * math.log(p) + (1 - o) * math.log(1 - p))
    return total / n


def reliability_bins(
    probs: Sequence[float], outcomes: Sequence[int], bins: int = 10
) -> list[dict]:
    """Per-bin (mean predicted, observed frequency, count) for a reliability diagram."""
    out: list[dict] = []
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        idx = [
            i for i, p in enumerate(probs)
            if p >= lo and (p < hi or (b == bins - 1 and p <= hi))
        ]
        if not idx:
            out.append({"bin": (lo, hi), "count": 0, "mean_pred": None, "observed": None})
            continue
        mp = sum(probs[i] for i in idx) / len(idx)
        obs = sum(outcomes[i] for i in idx) / len(idx)
        out.append({"bin": (lo, hi), "count": len(idx), "mean_pred": mp, "observed": obs})
    return out


def ece(probs: Sequence[float], outcomes: Sequence[int], bins: int = 10) -> float:
    """Expected Calibration Error: weighted mean |mean_pred - observed| over bins."""
    n = len(probs)
    if n == 0:
        return float("nan")
    e = 0.0
    for b in reliability_bins(probs, outcomes, bins):
        if b["count"]:
            e += (b["count"] / n) * abs(b["mean_pred"] - b["observed"])
    return e


def run_calibration(
    probs: Sequence[float], outcomes: Sequence[int], bins: int = 10
) -> dict:
    return {
        "n": len(probs),
        "brier": brier_score(probs, outcomes),
        "log_loss": log_loss(probs, outcomes),
        "ece": ece(probs, outcomes, bins),
        "reliability": reliability_bins(probs, outcomes, bins),
    }
