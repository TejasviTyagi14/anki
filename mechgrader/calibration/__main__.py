"""``python -m mechgrader.calibration`` — demonstrate the calibration metrics on a
clearly-labeled SIMULATION (no real review data exists yet).

It shows that a well-calibrated predictor yields low Brier/ECE, while an
overconfident one is flagged by higher ECE — proving the metric works — then
states honestly that real calibration awaits real longitudinal reviews.
"""

from __future__ import annotations

import random
import sys

from . import run_calibration


def _simulate(n: int, seed: int, distort: float) -> tuple[list[float], list[int]]:
    """Draw true probabilities, sample outcomes, and return a predictor that is
    distorted toward 0/1 by `distort` (0 = perfectly calibrated, >0 = overconfident)."""
    rng = random.Random(seed)
    probs: list[float] = []
    outcomes: list[int] = []
    for _ in range(n):
        true_p = rng.random()
        outcomes.append(1 if rng.random() < true_p else 0)
        pred = true_p + distort * ((1.0 if true_p >= 0.5 else 0.0) - true_p)
        probs.append(min(1.0, max(0.0, pred)))
    return probs, outcomes


def _report(name: str, probs, outcomes) -> dict:
    r = run_calibration(probs, outcomes, bins=10)
    print(f"\n{name}  (n={r['n']})")
    print(f"  Brier={r['brier']:.4f}  log_loss={r['log_loss']:.4f}  ECE={r['ece']:.4f}")
    print("  reliability (bin -> mean_pred / observed / count):")
    for b in r["reliability"]:
        if b["count"]:
            lo, hi = b["bin"]
            print(f"    [{lo:.1f},{hi:.1f}) pred={b['mean_pred']:.2f} obs={b['observed']:.2f} n={b['count']}")
    return r


def main() -> int:
    print("=" * 72)
    print("MechGrader memory calibration — SIMULATED demo (no real reviews yet)")
    print("=" * 72)
    print("NOTE: real calibration needs FSRS predicted P(recall) vs actual recall")
    print("from the revlog (real longitudinal reviews). This demonstrates the metric")
    print("machinery and that it DETECTS miscalibration; it is not a claim about the")
    print("real model. See docs/model_memory.md / docs/results.md (Section 9 honesty).")

    well = _report("Well-calibrated predictor", *_simulate(5000, seed=0, distort=0.0))
    over = _report("Overconfident predictor", *_simulate(5000, seed=0, distort=0.6))

    print("\nSanity: overconfident ECE should exceed well-calibrated ECE ->",
          f"{over['ece']:.4f} > {well['ece']:.4f}:",
          "PASS" if over["ece"] > well["ece"] else "UNEXPECTED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
