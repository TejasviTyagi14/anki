#!/usr/bin/env python3
"""Stage 3: memory-calibration metric tests (pure stdlib).

Run:  PYTHONPATH=. python3 mechgrader/tests/test_calibration.py
"""

from __future__ import annotations

import math
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from mechgrader.calibration import brier_score, ece, log_loss, reliability_bins, run_calibration


def test_brier_score_known_values():
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0
    assert abs(brier_score([0.5, 0.5], [1, 0]) - 0.25) < 1e-12


def test_log_loss_known_values():
    assert abs(log_loss([0.5], [1]) - math.log(2)) < 1e-9
    assert log_loss([1.0], [1]) < 1e-9  # perfect (clipped), ~0


def test_ece_zero_when_calibrated():
    probs = [0.5] * 100
    outcomes = [1] * 50 + [0] * 50  # observed freq 0.5 == mean pred 0.5
    assert ece(probs, outcomes, bins=10) < 1e-9


def test_ece_flags_miscalibration():
    probs = [0.9] * 100
    outcomes = [0] * 100  # predicted 0.9 but never recalled
    assert abs(ece(probs, outcomes, bins=10) - 0.9) < 1e-9


def test_reliability_bins_partition():
    probs = [0.05, 0.15, 0.95]
    outcomes = [0, 0, 1]
    bins = reliability_bins(probs, outcomes, bins=10)
    assert len(bins) == 10
    assert sum(b["count"] for b in bins) == 3
    # last bin includes p == 1.0 edge
    assert reliability_bins([1.0], [1], bins=10)[-1]["count"] == 1


def test_run_calibration_shape():
    r = run_calibration([0.2, 0.8], [0, 1], bins=5)
    assert set(r) >= {"n", "brier", "log_loss", "ece", "reliability"}
    assert r["n"] == 2


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\nOK: {len(tests)} calibration tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
