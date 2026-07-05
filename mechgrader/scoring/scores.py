"""The three scores: Memory, Performance, Readiness.

Pure stdlib (``math`` only), deterministic, offline-capable so desktop and
mobile compute identical numbers. See ``docs/model_memory.md``,
``docs/model_performance.md``, ``docs/model_readiness.md`` and
``docs/give_up_rule.md``.

Honesty contract (the single most important rule):
- A number presented as a measurement is NEVER fabricated, hardcoded,
  rounded-to-look-good, or interpolated.
- ``memory_score`` is a pass-through of the caller's FSRS P(recall).
- ``performance_by_type`` reports the exact observed proportion k/n.
- ``readiness`` refuses to project a number below the give-up line: it returns
  ``abstained: true`` with reasons and NO point/range.

Every SHOWN score dict carries: ``point``, ``range {low, high}``,
``pct_exam_covered``, ``how_sure``, ``last_updated`` (caller-supplied; may be
None), ``reasons[]`` and ``give_up_rule`` (a pointer). An ABSTAINED dict carries
``abstained: true`` + ``reasons`` and never any ``point``/``range`` number.
"""

from __future__ import annotations

import math
from typing import Any

from .give_up import (
    GIVE_UP_RULE_POINTER,
    MIN_COVERAGE_FRACTION,
    performance_gate,
    reaction_types,
    readiness_gate,
    weight_value,
)

__all__ = ["memory_score", "performance_by_type", "readiness"]

# --- Score bands / scales --------------------------------------------------
BAND_LOW = 118.0
BAND_HIGH = 132.0
BAND_WIDTH = BAND_HIGH - BAND_LOW  # 14 points per MCAT section
HALF_BAND = BAND_WIDTH / 2.0  # 7
TOTAL_LOW = 472.0
TOTAL_HIGH = 528.0
# Neutral band midpoint (125). Used ONLY as a clearly-labelled placeholder for
# MCAT sections with no evidence in the full-exam projection; never presented as
# a measurement.
BAND_MIDPOINT = (BAND_LOW + BAND_HIGH) / 2.0

# Coverage half-width budget (in score points). At zero weighted coverage the
# range can span the whole half-band; at full coverage it adds nothing and only
# the performance interval remains. Uncovered *high*-weight types drop weighted
# coverage the most, so they widen the range the most (uncertainty, not points).
COVERAGE_UNCERTAINTY_POINTS = HALF_BAND  # 7

DEFAULT_PASS_THRESHOLD = 0.5
# Placeholder calibration half-width for Memory until Stage 3 evidence exists.
# This is an explicit *uncertainty caveat*, not a measured calibration error.
DEFAULT_MEMORY_HALFWIDTH = 0.05

Z_95 = 1.959963984540054  # standard normal 97.5th percentile

MEMORY_SCALE = "P(recall) for this card (0-1); FSRS pass-through"
PERFORMANCE_SCALE = "P(correct mechanism | reaction type) (0-1)"
CHEMPHYS_SCALE = "projected MCAT Chem/Phys sub-score (118-132)"
TOTAL_SCALE = "projected MCAT total (472-528)"


# --- Small numeric helpers -------------------------------------------------
def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion, clamped to [0,1].

    Honest for small n (it never runs past 0/1 like the normal approximation).
    The observed proportion k/n is always bracketed (the interval is only ever
    widened to include it), so callers can rely on low <= k/n <= high.
    """
    if n <= 0:
        return (0.0, 1.0)
    phat = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))
    low = min(center - margin, phat)
    high = max(center + margin, phat)
    return (_clamp(low, 0.0, 1.0), _clamp(high, 0.0, 1.0))


def _grade_is_correct(grade: Any, pass_threshold: float) -> bool:
    """Interpret one mechanism grade as correct/incorrect.

    Accepts a bool, a numeric score (correct iff >= ``pass_threshold``), or a
    dict carrying ``correct``/``passed`` (bool) or ``score``/``grade`` (numeric).
    """
    if isinstance(grade, bool):
        return grade
    if isinstance(grade, (int, float)):
        return float(grade) >= pass_threshold
    if isinstance(grade, dict):
        for key in ("correct", "passed", "pass", "is_correct"):
            if key in grade:
                return bool(grade[key])
        for key in ("score", "grade", "value"):
            if key in grade:
                try:
                    return float(grade[key]) >= pass_threshold
                except (TypeError, ValueError):
                    return False
    return bool(grade)


def _pct_display(fraction: float) -> float:
    """Exact coverage ratio -> percentage rounded to 1 dp for display only."""
    return round(100.0 * fraction, 1)


# --- Model 1: Memory -------------------------------------------------------
def memory_score(
    p_recall: float | None,
    last_updated: Any = None,
    uncalibrated_halfwidth: float = DEFAULT_MEMORY_HALFWIDTH,
) -> dict[str, Any]:
    """P(recall) for one card, shown as a range (docs/model_memory.md).

    ``p_recall`` is a **pass-through** of Anki's FSRS retrievability supplied by
    the caller; it is never recomputed or fabricated here. It is displayed as a
    range with a calibration caveat (Stage 3 pending). No volume gate applies
    (memory is a per-card property); the only abstention is when the card has no
    review history yet (``p_recall is None``).

    The band is ``point +/- uncalibrated_halfwidth`` -- an explicit uncertainty
    caveat, not a measured calibration error -- clamped to [0,1], so always
    ``low <= point <= high``.
    """
    if p_recall is None:
        return {
            "abstained": True,
            "reasons": [
                "card has no review history yet - FSRS P(recall) unavailable"
            ],
            "how_sure": "abstaining - no review history",
            "pct_exam_covered": None,  # N/A: per-card property
            "last_updated": last_updated,
            "give_up_rule": GIVE_UP_RULE_POINTER,
            "scale": MEMORY_SCALE,
        }

    p = float(p_recall)
    if not (0.0 <= p <= 1.0):
        # Do not silently coerce a bad input into a fabricated number.
        raise ValueError(
            f"p_recall must be in [0,1] or None (FSRS pass-through), got {p_recall!r}"
        )

    hw = max(0.0, float(uncalibrated_halfwidth))
    low = _clamp(p - hw, 0.0, 1.0)
    high = _clamp(p + hw, 0.0, 1.0)
    return {
        "abstained": False,
        "point": p,  # exact FSRS pass-through
        "range": {"low": low, "high": high},
        "pct_exam_covered": None,  # N/A: memory is a per-card property
        "how_sure": (
            "uncalibrated - FSRS point shown with a placeholder "
            f"+/-{hw:g} band pending Stage 3 calibration; not yet validated"
        ),
        "last_updated": last_updated,
        "reasons": [
            "FSRS retrievability pass-through (not fabricated, not rounded)",
            "calibration evidence pending (Stage 3)",
        ],
        "give_up_rule": GIVE_UP_RULE_POINTER,
        "scale": MEMORY_SCALE,
    }


def _performance_how_sure(n: int) -> str:
    if n >= 20:
        level = "moderate"
    elif n >= 8:
        level = "low"
    else:
        level = "very low"
    return f"{level} - {n} graded attempts; held-out validation pending (Stage 3)"


# --- Model 2: Performance --------------------------------------------------
def performance_by_type(
    grades_by_type: dict[str, Any],
    last_updated: Any = None,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
) -> dict[str, dict[str, Any]]:
    """P(correct mechanism) per reaction type (docs/model_performance.md).

    ``grades_by_type`` maps a reaction-type id to an iterable of per-attempt
    mechanism grades (see ``_grade_is_correct`` for accepted grade shapes).

    Each type is scored only with >= 3 graded attempts (the per-type give-up
    gate); otherwise it abstains. When scored, ``point`` is the EXACT observed
    proportion k/n (a real measurement, never fabricated) and ``range`` is its
    95% Wilson interval. Returns ``{type_id: score_dict}``.
    """
    result: dict[str, dict[str, Any]] = {}
    for rtype, grades in grades_by_type.items():
        items = list(grades or [])
        n = len(items)
        gate = performance_gate(n)
        if gate["abstained"]:
            result[str(rtype)] = {
                "abstained": True,
                "attempts": n,
                "reasons": gate["reasons"],
                "how_sure": "abstaining - insufficient attempts",
                "pct_exam_covered": None,  # per-type; N/A
                "last_updated": last_updated,
                "give_up_rule": GIVE_UP_RULE_POINTER,
                "scale": PERFORMANCE_SCALE,
            }
            continue
        k = sum(1 for g in items if _grade_is_correct(g, pass_threshold))
        point = k / n  # exact observed proportion
        low, high = _wilson_interval(k, n)
        result[str(rtype)] = {
            "abstained": False,
            "point": point,
            "range": {"low": low, "high": high},
            "attempts": n,
            "correct": k,
            "pct_exam_covered": None,  # per-type; N/A
            "how_sure": _performance_how_sure(n),
            "last_updated": last_updated,
            "reasons": [
                f"P(correct) = {k}/{n} observed mechanism grades (not fabricated)",
                "95% Wilson interval; held-out/paraphrase validation pending (Stage 3)",
            ],
            "give_up_rule": GIVE_UP_RULE_POINTER,
            "scale": PERFORMANCE_SCALE,
        }
    return result


# --- Model 3: Readiness ----------------------------------------------------
def _section_coverage(
    performance: dict[str, dict[str, Any]],
    outline: list[dict[str, Any]],
    section: str | None,
) -> dict[str, Any]:
    """Weighted coverage of one outline section by *scored* reaction types.

    A type counts as covered only when its Performance is available and not
    abstained (i.e. it cleared the >=3-attempt gate). Weighted by outline
    emphasis so uncovered high-weight types drop coverage the most.
    """
    types = [rt for rt in outline if section is None or rt.get("section") == section]
    total_w = sum(weight_value(rt.get("weight")) for rt in types)
    scored: list[dict[str, Any]] = []
    covered_w = 0.0
    for rt in types:
        entry = performance.get(str(rt["id"]))
        if (
            entry
            and not entry.get("abstained", True)
            and isinstance(entry.get("point"), (int, float))
        ):
            scored.append(rt)
            covered_w += weight_value(rt.get("weight"))
    return {
        "types": types,
        "scored": scored,
        "scored_ids": {str(rt["id"]) for rt in scored},
        "total_w": total_w,
        "covered_w": covered_w,
        "fraction": (covered_w / total_w) if total_w > 0 else 0.0,
    }


def _project_section(
    performance: dict[str, dict[str, Any]],
    outline: list[dict[str, Any]],
    section: str | None,
    coverage_uncertainty_points: float,
) -> dict[str, Any] | None:
    """Map emphasis-weighted performance of a section to the 118-132 band.

    Returns None when the section has no scored type. See ``readiness`` for the
    full, stated mapping formula.
    """
    cov = _section_coverage(performance, outline, section)
    if not cov["scored"] or cov["covered_w"] <= 0:
        return None

    num_p = num_lo = num_hi = 0.0
    min_n: int | None = None
    for rt in cov["scored"]:
        w = weight_value(rt.get("weight"))
        e = performance[str(rt["id"])]
        num_p += w * float(e["point"])
        num_lo += w * float(e["range"]["low"])
        num_hi += w * float(e["range"]["high"])
        n = int(e.get("attempts", 0))
        min_n = n if min_n is None else min(min_n, n)

    cw = cov["covered_w"]
    p_hat = num_p / cw
    p_lo = num_lo / cw
    p_hi = num_hi / cw

    point = BAND_LOW + BAND_WIDTH * p_hat
    perf_low = BAND_LOW + BAND_WIDTH * p_lo
    perf_high = BAND_LOW + BAND_WIDTH * p_hi

    c = cov["fraction"]
    u = coverage_uncertainty_points * (1.0 - c)  # coverage-gap half-width

    point = _clamp(point, BAND_LOW, BAND_HIGH)
    low = _clamp(perf_low - u, BAND_LOW, BAND_HIGH)
    high = _clamp(perf_high + u, BAND_LOW, BAND_HIGH)
    low = min(low, point)
    high = max(high, point)

    uncovered_high = [
        str(rt["id"])
        for rt in cov["types"]
        if str(rt.get("weight", "")).strip().lower() == "high"
        and str(rt["id"]) not in cov["scored_ids"]
    ]
    return {
        "point": point,
        "low": low,
        "high": high,
        "coverage_fraction": c,
        "min_n": min_n if min_n is not None else 0,
        "n_scored": len(cov["scored"]),
        "n_total": len(cov["types"]),
        "uncovered_high": uncovered_high,
    }


def _readiness_how_sure(coverage_fraction: float, min_n: int) -> str:
    if coverage_fraction >= 0.85 and min_n >= 10:
        level = "moderate"
    elif coverage_fraction >= 0.60 and min_n >= 5:
        level = "low"
    else:
        level = "very low"
    return (
        f"{level} - coverage-weighted projection; method stated but NOT yet "
        f"validated against real MCAT outcomes (Stage 3 pending); based on "
        f"{round(coverage_fraction * 100)}% weighted Chem/Phys coverage"
    )


def _full_projection(
    performance: dict[str, dict[str, Any]],
    outline: list[dict[str, Any]],
    coverage_uncertainty_points: float,
    last_updated: Any,
) -> dict[str, Any]:
    """Optional full 472-528 projection (docs/model_readiness.md step 5).

    Shown only when weighted coverage crosses the give-up threshold in BOTH the
    Chem/Phys and Bio/Biochem orgo sections. Even then it is a heavy
    extrapolation: the two non-orgo MCAT sections (CARS, Psych/Soc) have NO
    evidence and are represented by an explicitly-labelled neutral band midpoint
    (not a measurement) with the full 118-132 ignorance folded into the range.
    Default is Chem/Phys only -> this abstains.
    """
    cp = _project_section(performance, outline, "chem_phys", coverage_uncertainty_points)
    bb = _project_section(performance, outline, "bio_biochem", coverage_uncertainty_points)
    cp_cov = cp["coverage_fraction"] if cp else 0.0
    bb_cov = bb["coverage_fraction"] if bb else 0.0

    if not (cp and bb and cp_cov >= MIN_COVERAGE_FRACTION and bb_cov >= MIN_COVERAGE_FRACTION):
        reasons = ["full 472-528 projection withheld - default is Chem/Phys only"]
        if bb_cov < MIN_COVERAGE_FRACTION:
            reasons.append(
                f"bio_biochem weighted coverage {round(bb_cov * 100)}% "
                f"< {round(MIN_COVERAGE_FRACTION * 100)}%"
            )
        if cp_cov < MIN_COVERAGE_FRACTION:
            reasons.append(
                f"chem_phys weighted coverage {round(cp_cov * 100)}% "
                f"< {round(MIN_COVERAGE_FRACTION * 100)}%"
            )
        return {
            "abstained": True,
            "reasons": reasons,
            "give_up_rule": GIVE_UP_RULE_POINTER,
            "scale": TOTAL_SCALE,
        }

    # Two orgo-relevant sub-scores from evidence; two non-orgo sections unknown.
    point = cp["point"] + bb["point"] + 2 * BAND_MIDPOINT
    low = _clamp(cp["low"] + bb["low"] + 2 * BAND_LOW, TOTAL_LOW, TOTAL_HIGH)
    high = _clamp(cp["high"] + bb["high"] + 2 * BAND_HIGH, TOTAL_LOW, TOTAL_HIGH)
    point = _clamp(point, TOTAL_LOW, TOTAL_HIGH)
    low = min(low, point)
    high = max(high, point)
    return {
        "abstained": False,
        "point": point,
        "range": {"low": low, "high": high},
        "pct_exam_covered": _pct_display((cp_cov + bb_cov) / 2.0),
        "how_sure": "very low - extrapolation; most MCAT content unassessed",
        "last_updated": last_updated,
        "reasons": [
            "Chem/Phys & Bio/Biochem sub-scores reflect orgo mechanisms only, "
            "not full section content",
            "CARS and Psych/Soc have NO evidence - neutral band-midpoint "
            "placeholders (NOT measurements); their full 118-132 ignorance is "
            "folded into the range",
            "very wide range; unvalidated (Stage 3 pending)",
        ],
        "give_up_rule": GIVE_UP_RULE_POINTER,
        "scale": TOTAL_SCALE,
        "assumptions": {
            "non_orgo_sections": ["CARS", "psych_soc"],
            "placeholder_point_each": BAND_MIDPOINT,
        },
    }


def readiness(
    performance_by_type: dict[str, dict[str, Any]],
    coverage_outline: Any,
    attempts_summary: Any,
    last_updated: Any = None,
    section: str = "chem_phys",
    coverage_uncertainty_points: float = COVERAGE_UNCERTAINTY_POINTS,
) -> dict[str, Any]:
    """Projected MCAT Chem/Phys sub-score (118-132) with a range and how-sure.

    Inputs
    ------
    performance_by_type : output of :func:`performance_by_type` (per-type dicts
        with ``point``/``range``/``attempts``; abstained types are ignored as
        evidence and count as uncovered).
    coverage_outline : the parsed ``mcat_orgo_outline.json`` (weights + sections).
    attempts_summary : total + per-type graded-attempt counts for the give-up
        rule (a wrapper dict with ``attempts_by_type``/``total_attempts`` or a
        bare ``{type_id: count}`` mapping).

    Give-up rule
    ------------
    This calls :func:`give_up.readiness_gate` FIRST. If the rule is not met it
    returns ``{"abstained": True, "reasons": [...]}`` with NO numeric score
    (no ``point``, no ``range``) -- abstaining is a real code path.

    The mapping (stated, monotonic; coverage adds uncertainty, not points)
    ------------------------------------------------------------------------
    For the target ``section`` (default ``chem_phys``), with numeric emphasis
    weight ``w = {high:3, medium:2, low:1}`` per reaction type and the set
    ``S`` of *scored* types (Performance available, >=3 attempts):

        P_hat = sum_{i in S} w_i * point_i  / sum_{i in S} w_i      (weighted mean)
        P_lo  = sum_{i in S} w_i * low_i    / sum_{i in S} w_i
        P_hi  = sum_{i in S} w_i * high_i   / sum_{i in S} w_i
        C     = sum_{i in S} w_i / sum_{i in section} w_i           (weighted coverage)

        point = 118 + 14 * P_hat                                    (monotonic)
        U     = coverage_uncertainty_points * (1 - C)              (coverage gap)
        low   = clamp(118 + 14 * P_lo  - U, 118, 132)
        high  = clamp(118 + 14 * P_hi  + U, 118, 132)

    ``point`` depends only on performance on covered types, so uncovered
    (especially high-weight) types never add points -- they shrink ``C`` and so
    widen the range ``U`` (uncertainty, not points). The interval is expanded if
    needed so ``low <= point <= high``.

    Output
    ------
    Default is Chem/Phys only. A full 472-528 projection is attached under
    ``full_projection`` only if coverage crosses the threshold in both orgo
    sections, always with a wide range + coverage caveat (otherwise it abstains).
    """
    # Give-up rule FIRST: no projection below the line.
    gate = readiness_gate(attempts_summary, coverage_outline)
    outline = reaction_types(coverage_outline)

    # Coverage is a diagnostic (not the score) -> safe to show even when abstaining.
    cov = _section_coverage(performance_by_type, outline, section)
    pct_covered = _pct_display(cov["fraction"])

    if gate["abstained"]:
        return {
            "abstained": True,
            "reasons": ["Readiness abstained per give-up rule:"] + gate["reasons"],
            "how_sure": "abstaining - insufficient data (see reasons)",
            "pct_exam_covered": pct_covered,  # coverage %, never a 118-132 score
            "last_updated": last_updated,
            "give_up_rule": GIVE_UP_RULE_POINTER,
            "scale": CHEMPHYS_SCALE,
        }

    proj = _project_section(
        performance_by_type, outline, section, coverage_uncertainty_points
    )
    if proj is None:
        # Defensive: rule passed but no scored type in this section.
        return {
            "abstained": True,
            "reasons": [
                "no scored reaction types in section "
                f"'{section}' - nothing to project"
            ],
            "how_sure": "abstaining - no in-section evidence",
            "pct_exam_covered": pct_covered,
            "last_updated": last_updated,
            "give_up_rule": GIVE_UP_RULE_POINTER,
            "scale": CHEMPHYS_SCALE,
        }

    reasons = [
        f"projected from {proj['n_scored']}/{proj['n_total']} {section} reaction "
        f"types ({_pct_display(proj['coverage_fraction']):g}% weighted coverage)",
        "mapping: point = 118 + 14 x (emphasis-weighted mean P(correct) over "
        "covered types); coverage gaps widen the range, they do not add points",
        "method stated but NOT yet validated against real MCAT outcomes "
        "(Stage 3 pending)",
    ]
    if proj["uncovered_high"]:
        reasons.append(
            "uncovered high-weight types widen the range: "
            + ", ".join(proj["uncovered_high"])
        )

    return {
        "abstained": False,
        "point": proj["point"],
        "range": {"low": proj["low"], "high": proj["high"]},
        "pct_exam_covered": _pct_display(proj["coverage_fraction"]),
        "how_sure": _readiness_how_sure(proj["coverage_fraction"], proj["min_n"]),
        "last_updated": last_updated,
        "reasons": reasons,
        "give_up_rule": GIVE_UP_RULE_POINTER,
        "scale": CHEMPHYS_SCALE,
        "full_projection": _full_projection(
            performance_by_type, outline, coverage_uncertainty_points, last_updated
        ),
    }
