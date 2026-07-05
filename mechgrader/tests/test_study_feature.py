#!/usr/bin/env python3
"""Stage 3: study-feature experiment harness tests (pure stdlib).

Tests that the harness is deterministic, produces valid three-arm output with
ranges, and that the learner model is FAIR (interleaving does NOT help when there
is nothing to discriminate, and only helps once confusability is high) — i.e. the
sim isn't rigged to always favor interleaving.

Run:  PYTHONPATH=. python3 mechgrader/tests/test_study_feature.py
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from mechgrader.experiment import confusability_sweep, run_experiment


def test_deterministic():
    assert run_experiment(seed=0) == run_experiment(seed=0)


def test_three_arms_valid_with_ranges():
    r = run_experiment(seed=0)
    for arm in ("interleaved", "blocked", "plain"):
        a = r["arms"][arm]
        assert 0.0 <= a["mean"] <= 1.0
        assert a["range"]["low"] <= a["mean"] <= a["range"]["high"]
        assert a["n"] == r["params"]["n_learners"]


def test_fair_no_free_lunch_at_zero_confusability():
    # With nothing to discriminate, interleaving's switch cost means it does not
    # beat blocked (the model has no baked-in interleaving bonus).
    r = run_experiment(seed=0, params={"confusability": 0.0})
    assert r["arms"]["interleaved"]["mean"] <= r["arms"]["blocked"]["mean"] + 1e-9


def test_helps_only_when_confusable():
    r = run_experiment(seed=0, params={"confusability": 2.4})
    assert r["arms"]["interleaved"]["mean"] >= r["arms"]["blocked"]["mean"]


def test_sweep_is_monotone_in_confusability():
    sweep = confusability_sweep(seed=0)
    deltas = [row["delta"] for row in sweep]
    # interleaving's advantage grows as families get more confusable
    assert deltas[0] <= deltas[-1]
    assert deltas[0] <= 0.0 <= deltas[-1] + 1e-9  # crosses from not-helping to helping


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\nOK: {len(tests)} study-feature tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
