#!/usr/bin/env python3
"""Stage 2: eval-harness metric tests with SYNTHETIC graders — no RDKit, no API
key, no network. Proves the metrics are correct, held-out-only, and that the
pre-registered cutoff logic is honest (AI must clear absolutes AND beat the
baseline).

Run:
    PYTHONPATH=. python3 mechgrader/tests/test_eval.py
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from mechgrader.eval import compare as C
from mechgrader.eval import harness as H


def _item(id_: str, split: str, target: int, human: int) -> dict:
    # The grader only sees (attempt, reference); we encode the intended score in
    # the attempt so a synthetic grader can echo it.
    return {
        "id": id_,
        "split": split,
        "reaction_type": "SN1",
        "reference": {"steps": []},
        "attempt": {"steps": [], "_target": target},
        "human_grade": human,
    }


GOLD = [
    _item("h1", "heldout", 95, 95),
    _item("h2", "heldout", 20, 20),
    _item("h3", "heldout", 80, 80),
    _item("h4", "heldout", 10, 10),
    _item("t1", "train", 50, 50),  # must be IGNORED on the heldout split
]


def perfect(attempt, reference):
    s = int(attempt.get("_target", 0))
    return {"score": s, "passed": s >= H.PASS_CUTOFF}


def always_pass(attempt, reference):
    return {"score": 100, "passed": True}


def test_perfect_grader_agrees_and_has_no_wrong_grades():
    m = H.run_eval(GOLD, perfect, seed=0)
    assert m["n_items"] == 4, "heldout only"
    assert "t1" not in m["evaluated_ids"], "train item must not be evaluated"
    assert m["agreement"] == 1.0, m["agreement"]
    assert m["wrong_grade_rate"] == 0.0, m["wrong_grade_rate"]
    assert m["score_pearson"] is not None and m["score_pearson"] > 0.99


def test_biased_always_pass_grader_is_confidently_wrong():
    m = H.run_eval(GOLD, always_pass, seed=0)
    # h2 (20) and h4 (10) are human-fail but graded pass -> false passes.
    assert m["confusion"]["fp"] >= 2, m["confusion"]
    assert m["wrong_grade_rate"] > 0.0
    assert m["agreement"] < 1.0


def test_run_eval_is_heldout_only():
    assert H.run_eval(GOLD, perfect, split="heldout")["n_items"] == 4
    assert H.run_eval(GOLD, perfect, split="train")["n_items"] == 1


def test_correlation_is_honest():
    assert abs(H.pearson([1, 2, 3, 4], [1, 2, 3, 4]) - 1.0) < 1e-9
    assert abs(H.pearson([1, 2, 3, 4], [4, 3, 2, 1]) + 1.0) < 1e-9
    assert abs(H.spearman([1, 2, 3, 4], [1, 4, 9, 16]) - 1.0) < 1e-9  # monotone nonlinear
    assert H.pearson([5, 5, 5], [1, 2, 3]) is None  # no variance -> undefined, not faked


def test_cutoffs_pass_when_ai_clears_absolutes_and_beats_baseline():
    baseline = {"agreement": 0.80, "wrong_grade_rate": 0.10, "score_pearson": 0.60}
    ai = {"agreement": 0.90, "wrong_grade_rate": 0.03, "score_pearson": 0.80}
    v = C.evaluate_cutoffs(baseline, ai)
    assert v["passed"] is True, v


def test_cutoffs_fail_when_absolute_agreement_missed():
    baseline = {"agreement": 0.70, "wrong_grade_rate": 0.10, "score_pearson": 0.50}
    ai = {"agreement": 0.82, "wrong_grade_rate": 0.03, "score_pearson": 0.80}  # 0.82 < 0.85
    assert C.evaluate_cutoffs(baseline, ai)["passed"] is False


def test_cutoffs_fail_when_ai_does_not_beat_baseline():
    baseline = {"agreement": 0.95, "wrong_grade_rate": 0.02, "score_pearson": 0.90}
    ai = {"agreement": 0.90, "wrong_grade_rate": 0.03, "score_pearson": 0.80}  # worse than baseline
    assert C.evaluate_cutoffs(baseline, ai)["passed"] is False


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\nOK: {len(tests)} eval-harness tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
