#!/usr/bin/env python3
"""Stage-1 tests for the three scores + the give-up rule.

Pure stdlib, deterministic, offline. Runs two ways (either is fine):

    python3 -m pytest mechgrader/tests/test_scoring.py -q
    python3 mechgrader/tests/test_scoring.py

The single most important property under test: below the give-up line the
Readiness projection ABSTAINS and leaks NO numeric score; above the line it
returns a point inside the MCAT Chem/Phys band [118, 132] with a bracketing
range. Every ``point`` is a real measurement (FSRS pass-through or observed
k/n), never fabricated.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from mechgrader.scoring.give_up import (  # noqa: E402
    performance_gate,
    readiness_gate,
)
from mechgrader.scoring.scores import (  # noqa: E402
    memory_score,
    performance_by_type,
    readiness,
)

_OUTLINE_PATH = _REPO_ROOT / "data" / "coverage" / "mcat_orgo_outline.json"


def _load_outline() -> dict:
    with open(_OUTLINE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


OUTLINE = _load_outline()
CHEM_PHYS_IDS = [
    rt["id"] for rt in OUTLINE["reaction_types"] if rt["section"] == "chem_phys"
]
HIGH_IDS = [rt["id"] for rt in OUTLINE["reaction_types"] if rt["weight"] == "high"]


# --- helpers ---------------------------------------------------------------
def _grades(correct: int, total: int) -> list[bool]:
    """A deterministic grade list with ``correct`` passes out of ``total``."""
    assert 0 <= correct <= total
    return [True] * correct + [False] * (total - correct)


def _iter_numbers(obj) -> list[float]:
    """Every numeric (non-bool) value nested anywhere in ``obj``."""
    out: list[float] = []
    if isinstance(obj, bool):
        return out
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_iter_numbers(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_iter_numbers(v))
    return out


def _assert_no_readiness_number(result: dict) -> None:
    """No numeric score present anywhere: no point/range and nothing in-band."""
    assert result["abstained"] is True
    assert "point" not in result, result
    assert "range" not in result, result
    for num in _iter_numbers(result):
        assert not (118.0 <= num <= 132.0), f"leaked in-band number {num}: {result}"


_SHOWN_KEYS = {
    "point",
    "range",
    "pct_exam_covered",
    "how_sure",
    "last_updated",
    "reasons",
    "give_up_rule",
}


def _assert_shown_contract(result: dict) -> None:
    assert result["abstained"] is False
    for key in _SHOWN_KEYS:
        assert key in result, f"shown score missing '{key}': {result}"
    lo = result["range"]["low"]
    hi = result["range"]["high"]
    assert lo <= result["point"] <= hi, result


# --- fixtures --------------------------------------------------------------
def _below_threshold_inputs():
    """A little data: a few types, far below every give-up threshold."""
    grades_by_type = {
        "SN1": _grades(4, 5),
        "SN2": _grades(3, 5),
        "E1": _grades(3, 5),
    }
    attempts_summary = {
        "total_attempts": sum(len(g) for g in grades_by_type.values()),  # 15
        "attempts_by_type": {k: len(v) for k, v in grades_by_type.items()},
        "last_updated": None,
    }
    return grades_by_type, attempts_summary


def _above_threshold_inputs(correct: int = 7, total: int = 10):
    """All 16 Chem/Phys types covered well; Bio/Biochem left uncovered.

    Clears volume (160 >= 150), breadth (16/20 = 80% >= 60%) and depth (every
    high-weight type has 10 >= 3 attempts).
    """
    grades_by_type = {tid: _grades(correct, total) for tid in CHEM_PHYS_IDS}
    attempts_summary = {
        "total_attempts": sum(len(g) for g in grades_by_type.values()),
        "attempts_by_type": {k: len(v) for k, v in grades_by_type.items()},
        "last_updated": "2026-07-05T15:00:00Z",
    }
    return grades_by_type, attempts_summary


# --- tests: give-up rule ---------------------------------------------------
def test_readiness_gate_below_threshold_names_conditions():
    _, attempts = _below_threshold_inputs()
    gate = readiness_gate(attempts, OUTLINE)
    assert gate["abstained"] is True
    blob = " | ".join(gate["reasons"]).lower()
    # volume shortfall stated with the exact remaining count (150 - 15 = 135).
    assert "135 more" in blob
    assert "150" in blob
    # breadth shortfall named.
    assert "breadth" in blob
    # every uncovered high-weight type flagged for depth (e.g. EAS at 0/3).
    assert "eas" in blob


def test_readiness_gate_pass():
    _, attempts = _above_threshold_inputs()
    gate = readiness_gate(attempts, OUTLINE)
    assert gate == {"abstained": False, "reasons": []}


def test_performance_gate_threshold():
    assert performance_gate(2)["abstained"] is True
    assert performance_gate(3)["abstained"] is False
    assert "1 more" in " ".join(performance_gate(2)["reasons"])


# --- tests: Memory ---------------------------------------------------------
def test_memory_range_brackets_point():
    res = memory_score(0.8, last_updated="t0")
    assert res["abstained"] is False
    assert res["point"] == 0.8  # exact FSRS pass-through, not fabricated
    assert res["range"]["low"] <= res["point"] <= res["range"]["high"]
    assert res["last_updated"] == "t0"
    _assert_shown_contract(res)


def test_memory_passthrough_edges_and_no_history():
    # Clamped band still brackets the point at the [0,1] edges.
    for p in (0.0, 0.5, 1.0):
        res = memory_score(p)
        assert res["point"] == p
        assert res["range"]["low"] <= p <= res["range"]["high"]
    # No review history -> a real abstain path, no number.
    none_res = memory_score(None)
    assert none_res["abstained"] is True
    assert "point" not in none_res and "range" not in none_res


# --- tests: Performance ----------------------------------------------------
def test_performance_type_below_three_attempts_abstains():
    perf = performance_by_type(
        {
            "E1": _grades(1, 2),  # 2 attempts -> abstains
            "SN1": _grades(2, 3),  # 3 attempts -> scored
        }
    )
    assert perf["E1"]["abstained"] is True
    assert "point" not in perf["E1"] and "range" not in perf["E1"]
    assert perf["E1"]["attempts"] == 2

    assert perf["SN1"]["abstained"] is False
    assert perf["SN1"]["attempts"] == 3
    _assert_shown_contract(perf["SN1"])


def test_performance_point_is_exact_observed_proportion():
    perf = performance_by_type({"SN2": _grades(3, 4)})
    assert perf["SN2"]["point"] == 0.75  # exactly 3/4, not fabricated/rounded
    lo = perf["SN2"]["range"]["low"]
    hi = perf["SN2"]["range"]["high"]
    assert lo <= 0.75 <= hi


# --- tests: Readiness ------------------------------------------------------
def test_readiness_below_threshold_abstains_with_no_number():
    grades, attempts = _below_threshold_inputs()
    perf = performance_by_type(grades)
    res = readiness(perf, OUTLINE, attempts)
    _assert_no_readiness_number(res)
    assert res["reasons"], "abstention must state why"


def test_readiness_above_threshold_point_in_band_with_range():
    grades, attempts = _above_threshold_inputs(correct=7, total=10)
    perf = performance_by_type(grades, last_updated=attempts["last_updated"])
    res = readiness(perf, OUTLINE, attempts, last_updated=attempts["last_updated"])

    _assert_shown_contract(res)
    point = res["point"]
    lo = res["range"]["low"]
    hi = res["range"]["high"]

    # point inside the MCAT Chem/Phys band, with a bracketing in-band range.
    assert 118.0 <= point <= 132.0
    assert lo <= point <= hi
    assert 118.0 <= lo <= hi <= 132.0

    # Mapping check: full weighted coverage -> point = 118 + 14 * 0.7 = 127.8.
    assert abs(point - 127.8) < 1e-6, point
    assert res["pct_exam_covered"] == 100.0
    assert res["last_updated"] == "2026-07-05T15:00:00Z"

    # Default output is Chem/Phys only; full 472-528 stays withheld (no Bio cov).
    assert res["full_projection"]["abstained"] is True


def test_readiness_point_monotonic_in_performance():
    """Higher mechanism accuracy -> higher (or equal) projected sub-score."""
    lo_grades, lo_attempts = _above_threshold_inputs(correct=5, total=10)
    hi_grades, hi_attempts = _above_threshold_inputs(correct=9, total=10)
    lo_res = readiness(performance_by_type(lo_grades), OUTLINE, lo_attempts)
    hi_res = readiness(performance_by_type(hi_grades), OUTLINE, hi_attempts)
    assert lo_res["point"] < hi_res["point"]
    for res in (lo_res, hi_res):
        assert 118.0 <= res["point"] <= 132.0


def test_readiness_partial_coverage_widens_range():
    """Uncovered emphasis widens the band (uncertainty), not the point."""
    # Cover the 8 high types + 4 medium types (12/20 breadth = 60%), 13 each.
    covered = HIGH_IDS + [
        tid
        for tid in CHEM_PHYS_IDS
        if tid not in HIGH_IDS
    ][:4]
    grades = {tid: _grades(9, 13) for tid in covered}
    attempts = {
        "total_attempts": sum(len(g) for g in grades.values()),  # 156 >= 150
        "attempts_by_type": {k: len(v) for k, v in grades.items()},
    }
    res = readiness(performance_by_type(grades), OUTLINE, attempts)
    _assert_shown_contract(res)
    assert res["abstained"] is False
    assert res["pct_exam_covered"] < 100.0  # not fully covered
    # Range strictly wider than the fully-covered case at the same accuracy.
    full_grades, full_attempts = _above_threshold_inputs(correct=9, total=13)
    full_res = readiness(performance_by_type(full_grades), OUTLINE, full_attempts)
    partial_width = res["range"]["high"] - res["range"]["low"]
    full_width = full_res["range"]["high"] - full_res["range"]["low"]
    assert partial_width > full_width


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\nOK: {len(tests)} scoring tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
