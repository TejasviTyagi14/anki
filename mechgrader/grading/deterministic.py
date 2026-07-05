"""Deterministic MechGrader mechanism grader (Stage 1).

Grades a submitted structured mechanism against a reference mechanism of the
same shape by **reusing the chem-grader prototype's layered** :class:`Grader`.
No chemistry is reimplemented here -- RDKit / chem-grader do all parsing,
canonicalisation, atom mapping, transformation analysis, mechanism inference and
pathway alignment. This module is glue plus two honest, traceable extras:

* an **exact atom + formal-charge balance** check per step. chem-grader's own
  edge conservation only flags *carbon* changes (its edges are reactant->product
  single molecules with no reagents), but a MechGrader step lists every species,
  so we can check the full element/charge ledger and fold it into the score.
* a **canonical-identity product match** (final products compared by InChIKey).

Output is a flat MechGrader grade dict (see :func:`grade_mechanism`)::

    {
      "valid": bool,          # every submitted structure parses in RDKit
      "score": int,           # 0-100
      "product_match": bool,  # final products == reference (InChIKey multiset)
      "balance_ok": bool,     # every step conserves atoms and charge
      "per_step": [ {"step_index": int, "correct": bool, "reasons": [str]} ],
      "reasons": [str],       # itemised, traceable breakdown
      "passed": bool,         # valid & product_match & score >= threshold
      "threshold": int,
      "breakdown": {...},     # the chem-grader sub-scores + balanced fraction
      "summary": str,
    }
"""

from __future__ import annotations

from typing import Any, Optional

from chemgrader import Grader, GraderConfig
from chemgrader.structure_service import StructureService

from . import _convert
from ._convert import MechanismFormatError, MechanismSpec

# The stated pass threshold (out of 100). Reaching the correct product is also
# required to pass -- a plausible route to the wrong molecule is not a pass.
PASS_THRESHOLD = 70

# A mechanism that does not reproduce the reference's final product cannot score
# above this, no matter how tidy its steps look. This is a deliberate honesty
# guard: chem-grader identifies molecules by InChIKey, which treats some protons
# as mobile (e.g. R-OH2(+) . H2O reads the same as R-OH . H3O(+)), so its own
# pathway score can miss a wrong final product that our per-species check catches.
PRODUCT_MISS_CAP = 40


def grade_mechanism(
    submission: Any,
    reference: Any,
    *,
    pass_threshold: int = PASS_THRESHOLD,
    grader: Optional[Grader] = None,
    config: Optional[GraderConfig] = None,
) -> dict:
    """Grade ``submission`` against ``reference`` (both MechGrader mechanisms).

    Never raises on bad input: malformed shapes or unparseable SMILES come back
    as ``valid: false`` with a friendly message rather than a stack trace.
    """
    service = StructureService()
    grader = grader or Grader(service=service)

    # 1. shape validation (never raises out of here) -------------------------- #
    try:
        attempt_spec = _convert.parse_mechanism(submission)
        reference_spec = _convert.parse_mechanism(reference)
    except MechanismFormatError as exc:
        return _invalid_result(f"Couldn't read the mechanism: {exc}.", pass_threshold)

    # 2. structural validity (every SMILES must parse) ------------------------ #
    bad_attempt = _convert.find_unparseable(attempt_spec)
    if bad_attempt:
        message = (
            "Some structures couldn't be read as valid molecules: "
            + "; ".join(bad_attempt)
            + ". Check the SMILES for those species."
        )
        return _invalid_result(message, pass_threshold, per_step=_flag_bad_steps(bad_attempt, attempt_spec))

    bad_reference = _convert.find_unparseable(reference_spec)
    if bad_reference:
        message = (
            "The reference mechanism has invalid structures ("
            + "; ".join(bad_reference)
            + "); cannot grade against it."
        )
        # The submission itself is valid; we simply can't grade it.
        return _invalid_result(message, pass_threshold, valid=True)

    # 3. run chem-grader's layered grader ------------------------------------- #
    reference_graph = _convert.build_reaction_graph(reference_spec, "reference")
    attempt_graph = _convert.build_reaction_graph(attempt_spec, "attempt")
    result = grader.grade(reference_graph, attempt_graph, config or GraderConfig())
    edge_by_step = {edge.edge_id: edge for edge in result.edges}

    # 4. exact per-step balance + per-step verdicts --------------------------- #
    per_step: list[dict] = []
    balanced_flags: list[bool] = []
    for step in attempt_spec.steps:
        feedback = edge_by_step.get(f"e{step.index}")
        balanced, detail = _convert.step_balance(step)
        balanced_flags.append(balanced)
        correct, reasons = _step_verdict(feedback, balanced, detail)
        per_step.append({"step_index": step.index, "correct": correct, "reasons": reasons})

    balance_ok = all(balanced_flags)
    balanced_fraction = (sum(balanced_flags) / len(balanced_flags)) if balanced_flags else 1.0

    # 5. product identity ----------------------------------------------------- #
    product_match = _convert.species_multiset_keys(
        attempt_spec.final_products, service
    ) == _convert.species_multiset_keys(reference_spec.final_products, service)

    # 6. score: the 5-layer grade, scaled by the fraction of mass/charge-balanced
    #    steps (an unbalanced step is a real error chem-grader's carbon-only check
    #    can miss), then capped if the final product wasn't reproduced.
    #    Deterministic and fully explained in `reasons`.
    score = int(round(result.overall_score * balanced_fraction * 100))
    product_capped = False
    if not product_match and score > PRODUCT_MISS_CAP:
        score = PRODUCT_MISS_CAP
        product_capped = True
    passed = bool(product_match and score >= pass_threshold)

    reasons = _top_level_reasons(
        result, balanced_flags, balanced_fraction, product_match, product_capped,
        per_step, score, pass_threshold, passed,
    )

    return {
        "valid": True,
        "score": score,
        "product_match": bool(product_match),
        "balance_ok": bool(balance_ok),
        "per_step": per_step,
        "reasons": reasons,
        "passed": passed,
        "threshold": pass_threshold,
        "breakdown": {
            "structures": result.breakdown.nodes,
            "transformations": result.breakdown.transformations,
            "mechanisms": result.breakdown.mechanisms,
            "pathway": result.breakdown.pathway,
            "chem_overall": result.overall_score,
            "balanced_fraction": round(balanced_fraction, 4),
        },
        "summary": result.summary,
    }


# --------------------------------------------------------------------------- #
# per-step + top-level reasoning
# --------------------------------------------------------------------------- #
def _step_verdict(feedback, balanced: bool, balance_detail: str) -> tuple[bool, list[str]]:
    """Turn one chem-grader EdgeFeedback + our balance check into a verdict.

    A step is "correct" when it is a chemically plausible, mass/charge-balanced
    elementary step that matches the reference mechanism and whose stated
    mechanism (if any) isn't contradicted. Arrow-pushing is advisory only (it
    never gates the score in chem-grader) so it's surfaced but doesn't flip
    correctness.
    """
    reasons: list[str] = []
    if feedback is None:  # pragma: no cover - every step maps to an edge
        return False, ["internal error: no grader feedback for this step"]

    plausible = feedback.transformation_plausible
    if not plausible:
        if feedback.errors:
            reasons.extend(feedback.errors)
        else:
            reasons.extend(feedback.warnings or ["transformation is implausible or ambiguous"])

    if not balanced:
        reasons.append(f"does not conserve mass/charge: {balance_detail}")

    if feedback.mechanism_consistent is False:
        reasons.append("stated mechanism is inconsistent with the structural change")

    if not feedback.matches_reference:
        reasons.append("this step doesn't match the reference mechanism")

    # advisory arrow notes (do not affect correctness)
    if feedback.arrows_checked and not feedback.arrows_ok:
        for err in feedback.errors:
            if err not in reasons:
                reasons.append(f"arrow-pushing: {err}")

    correct = bool(
        plausible
        and balanced
        and feedback.matches_reference
        and feedback.mechanism_consistent is not False
    )
    if correct and not reasons:
        reasons.append("matches the reference step")
    return correct, reasons


def _top_level_reasons(
    result,
    balanced_flags: list[bool],
    balanced_fraction: float,
    product_match: bool,
    product_capped: bool,
    per_step: list[dict],
    score: int,
    pass_threshold: int,
    passed: bool,
) -> list[str]:
    breakdown = result.breakdown
    reasons: list[str] = [
        "5-layer grade: structures {:.0%}, transformations {:.0%}, mechanisms {:.0%}, "
        "pathway {:.0%} -> overall {:.0%}.".format(
            breakdown.nodes,
            breakdown.transformations,
            breakdown.mechanisms,
            breakdown.pathway,
            result.overall_score,
        )
    ]

    if all(balanced_flags):
        reasons.append("Every step conserves atoms and formal charge.")
    else:
        unbalanced = [i + 1 for i, ok in enumerate(balanced_flags) if not ok]
        reasons.append(
            "Atom/charge balance failed on step(s) {}; score scaled by the balanced "
            "fraction ({:.0%}).".format(unbalanced, balanced_fraction)
        )

    if product_match:
        reasons.append("Final product matches the reference.")
    else:
        message = "Final product does NOT match the reference (by canonical InChIKey)."
        if product_capped:
            message += f" Score capped at {score}/100."
        reasons.append(message)

    for entry in per_step:
        if not entry["correct"]:
            reasons.append(f"Step {entry['step_index'] + 1}: " + "; ".join(entry["reasons"]))

    reasons.extend(result.hints)

    verdict = "PASS" if passed else "FAIL"
    tail = "" if product_match else " (final product not reproduced)"
    reasons.append(f"Score {score}/100 vs threshold {pass_threshold} -> {verdict}{tail}.")
    return reasons


# --------------------------------------------------------------------------- #
# invalid-input results
# --------------------------------------------------------------------------- #
def _invalid_result(
    message: str,
    pass_threshold: int,
    *,
    valid: bool = False,
    per_step: Optional[list[dict]] = None,
) -> dict:
    return {
        "valid": valid,
        "score": 0,
        "product_match": False,
        "balance_ok": False,
        "per_step": per_step or [],
        "reasons": [message],
        "passed": False,
        "threshold": pass_threshold,
        "breakdown": {},
        "summary": message,
    }


def _flag_bad_steps(bad: list[str], spec: MechanismSpec) -> list[dict]:
    """Mark the steps that contain an unparseable structure as incorrect."""
    bad_step_numbers = set()
    for description in bad:
        # descriptions look like "step 3 reactant '...'": grab the number.
        parts = description.split()
        if len(parts) >= 2 and parts[0] == "step" and parts[1].isdigit():
            bad_step_numbers.add(int(parts[1]))
    return [
        {
            "step_index": step.index,
            "correct": False,
            "reasons": ["contains an unparseable structure"],
        }
        for step in spec.steps
        if (step.index + 1) in bad_step_numbers
    ]
