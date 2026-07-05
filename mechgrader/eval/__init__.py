"""MechGrader evaluation harness (Stage 2).

This package answers one question **before** any grading claim ships: *do the
grader's verdicts actually match a human's?* It does so honestly:

* The harness is **grader-agnostic** — you inject a ``grader_fn(attempt,
  reference) -> {"score", "passed", ...}``. The RDKit-only deterministic grader
  and the AI rubric grader are both graded by the *same* metrics code, so the
  comparison is apples-to-apples.
* Everything is **seeded and deterministic**: the same gold set + grader always
  produce the same numbers (including the bootstrap confidence intervals).
* The metrics logic depends on **stdlib only** — no RDKit, no API key, no
  numpy/pandas — so it can be unit-tested with canned "synthetic" graders.
* Metrics are computed on the **held-out** split only. Fitting or tuning on the
  held-out split is the one thing this whole exercise exists to prevent.

Modules
-------
- ``harness``  : the metrics (agreement, wrong-grade rate, Pearson/Spearman) and
                 :func:`~mechgrader.eval.harness.run_eval`; gold loading/validation.
- ``compare``  : the pre-registered cutoffs and the baseline-vs-AI comparison.
- ``ai_grader``: an honest, gated adapter that refuses to emit AI numbers unless
                 ``MECHGRADER_LLM_PROVIDER`` **and** a real API key are set.
- ``__main__`` : the ``make eval`` entry point (``python -m mechgrader.eval``).

See ``docs/ai_eval.md`` and ``mechgrader/eval/PREREGISTERED.md``.
"""

from __future__ import annotations

from .harness import (
    CLEARLY_CORRECT,
    PASS_CUTOFF,
    load_gold_items,
    pearson,
    run_eval,
    spearman,
    split_counts,
    validate_gold_item,
)

__all__ = [
    "PASS_CUTOFF",
    "CLEARLY_CORRECT",
    "run_eval",
    "pearson",
    "spearman",
    "load_gold_items",
    "validate_gold_item",
    "split_counts",
]
