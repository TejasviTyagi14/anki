"""Tests for the MechGrader deterministic mechanism grader.

These exercise :func:`mechgrader.grading.deterministic.grade_mechanism`, which
grades a submitted structured mechanism against a reference mechanism by reusing
the chem-grader prototype's layered ``Grader``.

Run from the repo root with the chem-grader venv (it provides RDKit), putting
both ``chem-grader/src`` and the repo root on ``PYTHONPATH``::

    cd /Users/artisingh/anki
    PYTHONPATH=chem-grader/src:. chem-grader/.venv/bin/python \
        -m pytest mechgrader/tests/test_deterministic_grader.py -q

The ``sys.path`` bootstrap below mirrors that so the file is also importable
when pytest is pointed straight at it, as long as it runs under an interpreter
that has RDKit installed (the chem-grader venv).
"""

from __future__ import annotations

import copy
import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_CHEM_SRC = os.path.join(_REPO_ROOT, "chem-grader", "src")
for _path in (_REPO_ROOT, _CHEM_SRC):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from mechgrader.grading.deterministic import PASS_THRESHOLD, grade_mechanism


# --------------------------------------------------------------------------- #
# Shared reference mechanism: SN1 of tert-butyl bromide in water (3 elementary
# steps), with atom-mapped SMILES so every atom is tracked across the arrow.
#   1. ionization:        (CH3)3C-Br            -> (CH3)3C(+)  +  Br(-)
#   2. nucleophilic add:  (CH3)3C(+) + H2O      -> (CH3)3C-OH2(+)
#   3. deprotonation:     (CH3)3C-OH2(+) + H2O  -> (CH3)3C-OH  +  H3O(+)
# --------------------------------------------------------------------------- #
TBU_BR = "[CH3:1][C:2]([CH3:3])([CH3:4])[Br:5]"
TBU_CATION = "[CH3:1][C+:2]([CH3:3])[CH3:4]"
BROMIDE = "[Br-:5]"
WATER = "[OH2:6]"
TBU_OXOCARBENIUM = "[CH3:1][C:2]([CH3:3])([CH3:4])[OH2+:6]"
WATER_BASE = "[OH2:7]"
TBU_OH = "[CH3:1][C:2]([CH3:3])([CH3:4])[OH:6]"
HYDRONIUM = "[OH3+:7]"


def reference_mechanism() -> dict:
    """A fresh copy of the reference SN1 mechanism (fresh so tests can mutate)."""
    return {
        "steps": [
            {
                "reactants": [TBU_BR],
                "arrows": [{"from": "bond:1-4", "to": "atom:4", "kind": "curved"}],
                "products": [TBU_CATION, BROMIDE],
            },
            {
                "reactants": [TBU_CATION, WATER],
                "arrows": [{"from": "lp:4", "to": "atom:1", "kind": "curved"}],
                "products": [TBU_OXOCARBENIUM],
            },
            {
                "reactants": [TBU_OXOCARBENIUM, WATER_BASE],
                "arrows": [{"from": "lp:6", "to": "atom:5", "kind": "curved"}],
                "products": [TBU_OH, HYDRONIUM],
            },
        ]
    }


REQUIRED_KEYS = {
    "valid": bool,
    "score": int,
    "product_match": bool,
    "balance_ok": bool,
    "per_step": list,
    "reasons": list,
    "passed": bool,
}


def _assert_schema(result: dict) -> None:
    for key, expected_type in REQUIRED_KEYS.items():
        assert key in result, f"missing key {key!r} in grade dict"
        assert isinstance(result[key], expected_type), (
            f"key {key!r} should be {expected_type.__name__}, got {type(result[key]).__name__}"
        )
    assert 0 <= result["score"] <= 100
    for entry in result["per_step"]:
        assert set(entry) >= {"step_index", "correct", "reasons"}
        assert isinstance(entry["step_index"], int)
        assert isinstance(entry["correct"], bool)
        assert isinstance(entry["reasons"], list)
    # reasons must be human-readable strings (traceable, never a raw traceback)
    assert result["reasons"], "reasons should never be empty"
    assert all(isinstance(r, str) for r in result["reasons"])


# --------------------------------------------------------------------------- #
# 1. identical attempt -> high score, product matches, passes
# --------------------------------------------------------------------------- #
def test_identical_attempt_scores_high_and_passes():
    ref = reference_mechanism()
    result = grade_mechanism(copy.deepcopy(ref), ref)

    _assert_schema(result)
    assert result["valid"] is True
    assert result["product_match"] is True
    assert result["balance_ok"] is True
    assert result["passed"] is True
    assert result["score"] >= 80, result["reasons"]
    assert result["score"] >= PASS_THRESHOLD
    assert all(step["correct"] for step in result["per_step"])
    assert len(result["per_step"]) == 3


# --------------------------------------------------------------------------- #
# 2. wrong final product -> product_match false, does not pass
# --------------------------------------------------------------------------- #
def test_wrong_final_product_does_not_match_and_fails():
    ref = reference_mechanism()
    attempt = reference_mechanism()
    # Same route, but the last step delivers tert-butyl chloride, not the alcohol.
    attempt["steps"][-1]["products"] = [
        "[CH3:1][C:2]([CH3:3])([CH3:4])[Cl:6]",
        HYDRONIUM,
    ]

    result = grade_mechanism(attempt, ref)

    _assert_schema(result)
    assert result["valid"] is True  # structures parse; the chemistry is just wrong
    assert result["product_match"] is False
    assert result["passed"] is False
    assert result["score"] < PASS_THRESHOLD
    # the final step should be flagged as not matching the reference
    assert result["per_step"][-1]["correct"] is False
    assert any("final product" in r.lower() for r in result["reasons"])


# --------------------------------------------------------------------------- #
# 3. partially-wrong mechanism -> partial score (right product, one bad step)
# --------------------------------------------------------------------------- #
def test_partially_wrong_mechanism_gets_partial_score():
    ref = reference_mechanism()
    identical = grade_mechanism(reference_mechanism(), ref)

    attempt = reference_mechanism()
    # Correct first two steps; the deprotonation drops the water base, so the
    # step no longer conserves mass/charge even though it still draws the right
    # final product (tert-butanol + hydronium).
    attempt["steps"][-1]["reactants"] = [TBU_OXOCARBENIUM]

    result = grade_mechanism(attempt, ref)

    _assert_schema(result)
    assert result["valid"] is True
    assert result["product_match"] is True  # correct final product is still drawn
    assert result["balance_ok"] is False  # but a step doesn't balance
    assert result["passed"] is False
    # "partial": strictly between a total miss and a perfect attempt
    assert 0 < result["score"] < identical["score"]
    # first two steps correct, the tampered third is not
    assert result["per_step"][0]["correct"] is True
    assert result["per_step"][1]["correct"] is True
    assert result["per_step"][2]["correct"] is False
    assert any("balance" in r.lower() or "conserve" in r.lower() for r in result["reasons"])


# --------------------------------------------------------------------------- #
# 4. invalid SMILES -> valid false with a friendly message (no stack trace)
# --------------------------------------------------------------------------- #
def test_invalid_smiles_reports_friendly_error():
    ref = reference_mechanism()
    attempt = reference_mechanism()
    attempt["steps"][1]["products"] = ["this-is-not-a-molecule"]

    result = grade_mechanism(attempt, ref)

    _assert_schema(result)
    assert result["valid"] is False
    assert result["passed"] is False
    assert result["score"] == 0
    message = " ".join(result["reasons"]).lower()
    assert "this-is-not-a-molecule" in message
    assert "couldn't be read" in message or "valid molecules" in message
    # friendly, not a Python traceback
    assert "traceback" not in message
    assert "error:" not in message


def test_malformed_input_is_handled_gracefully():
    ref = reference_mechanism()

    for bad in ({}, {"steps": []}, {"steps": [{"reactants": [], "products": [TBU_OH]}]}, "not json"):
        result = grade_mechanism(bad, ref)
        _assert_schema(result)
        assert result["valid"] is False
        assert result["passed"] is False
        assert result["score"] == 0


# --------------------------------------------------------------------------- #
# 5. the grade genuinely comes from reusing chem-grader's Grader
# --------------------------------------------------------------------------- #
def test_result_exposes_chem_grader_breakdown():
    ref = reference_mechanism()
    result = grade_mechanism(reference_mechanism(), ref)

    assert "breakdown" in result
    breakdown = result["breakdown"]
    # the four chem-grader layers plus the balance factor we fold in
    for key in ("structures", "transformations", "mechanisms", "pathway", "chem_overall"):
        assert key in breakdown
        assert 0.0 <= breakdown[key] <= 1.0
    assert breakdown["balanced_fraction"] == 1.0
