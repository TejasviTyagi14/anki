"""Card-generation quality check for MechGrader (rubric item 7f).

If MechCards are generated from a source, a *wrong* card is worse than no card,
so generated cards must be gated before they ship. This package builds that gate:

* :mod:`mechgrader.cardgen.check` — the deterministic checker. It compares each
  generated card's answer against a gold Q&A set (``data/gold_qa/gold_qa.json``)
  and classifies every card into exactly three buckets — ``correct_useful``,
  ``wrong`` (a factual mismatch/contradiction), and ``bad_teaching``
  (correct-but-vague/trivial/duplicate) — then reports the three counts and a
  pass/fail against a **pre-registered** cutoff, and lists the cards to block.
* :mod:`mechgrader.cardgen.generate` — the env-gated LLM generation SEAM. This is
  the only part that needs an API key; it is documented and injectable and is
  never exercised against a real API in tests.

The cutoff itself is pre-registered in ``PREREGISTERED.md`` and mirrored by
:data:`mechgrader.cardgen.check.DEFAULT_PASS_CUTOFF` so code and prose agree.
"""

from mechgrader.cardgen.check import (
    DEFAULT_PASS_CUTOFF,
    PassCutoff,
    blocked_cards,
    classify_card,
    duplicate_indices,
    is_trivial,
    load_gold_items,
    near_duplicate_pairs,
    run_cardgen_check,
    triviality_reasons,
)

__all__ = [
    "DEFAULT_PASS_CUTOFF",
    "PassCutoff",
    "blocked_cards",
    "classify_card",
    "duplicate_indices",
    "is_trivial",
    "load_gold_items",
    "near_duplicate_pairs",
    "run_cardgen_check",
    "triviality_reasons",
]
