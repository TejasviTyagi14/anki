"""The give-up rule (abstention), enforced in code — see ``docs/give_up_rule.md``.

Abstaining is a *feature, not a bug*: a "not enough data" message scores higher
than a fabricated number. This module never invents, rounds-to-look-good, or
interpolates a score; it only decides **whether** a score may be shown and, when
it may not, names exactly which condition failed and what is still needed.

Pure stdlib, deterministic, offline-capable so desktop and mobile agree.

Rule v1 (change only with a recorded reason). Readiness is shown ONLY when ALL:

1. Volume:  >= 150 graded mechanism attempts total.
2. Breadth: attempts span >= 60% of the MCAT orgo reaction-type outline.
3. Depth:   >= 3 graded attempts in EVERY ``high``-weight reaction type.

Per-type Performance gate: a reaction type is scored only with >= 3 graded
attempts; otherwise that single type abstains.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

__all__ = [
    "MIN_TOTAL_ATTEMPTS",
    "MIN_COVERAGE_FRACTION",
    "MIN_HIGH_WEIGHT_ATTEMPTS",
    "MIN_TYPE_ATTEMPTS",
    "WEIGHT_VALUES",
    "GIVE_UP_RULE_POINTER",
    "GiveUpRule",
    "DEFAULT_RULE",
    "readiness_gate",
    "performance_gate",
    "reaction_types",
    "weight_value",
    "high_weight_type_ids",
]

# --- Thresholds (v1 of docs/give_up_rule.md) -------------------------------
MIN_TOTAL_ATTEMPTS = 150
MIN_COVERAGE_FRACTION = 0.60
MIN_HIGH_WEIGHT_ATTEMPTS = 3
MIN_TYPE_ATTEMPTS = 3  # per-type Performance gate

# Qualitative outline emphasis -> numeric weight used ONLY for weighting/coverage.
# These are reasonable author estimates (see the outline's own note), NOT official
# AAMC numeric weights. Unknown weights fall back to the lowest tier.
WEIGHT_VALUES = {"high": 3.0, "medium": 2.0, "low": 1.0}

GIVE_UP_RULE_POINTER = (
    "docs/give_up_rule.md: Readiness needs >=150 graded attempts, attempts "
    "spanning >=60% of the reaction-type outline, and >=3 attempts in every "
    "high-weight reaction type; per-type Performance needs >=3 attempts."
)

# Metadata keys tolerated inside an ``attempts_summary`` mapping so a caller may
# pass a bare ``{type_id: count}`` dict without them being read as a reaction type.
_META_KEYS = {"attempts_by_type", "total_attempts", "total", "last_updated"}


# --- Outline helpers -------------------------------------------------------
def reaction_types(coverage_outline: Any) -> list[dict[str, Any]]:
    """Return the list of reaction-type records from a coverage outline.

    Accepts either the parsed ``mcat_orgo_outline.json`` object (a dict with a
    ``reaction_types`` list) or a bare list of reaction-type dicts. Records
    without an ``id`` are dropped. Never fabricates entries.
    """
    if isinstance(coverage_outline, dict):
        raw = coverage_outline.get("reaction_types", [])
    elif isinstance(coverage_outline, (list, tuple)):
        raw = coverage_outline
    else:
        raw = []
    return [rt for rt in raw if isinstance(rt, dict) and rt.get("id")]


def weight_value(weight: Any) -> float:
    """Map a qualitative outline weight (high/medium/low) to a numeric value.

    Unknown/missing weights fall back to the lowest tier so an unclassified type
    can never inflate a score.
    """
    return WEIGHT_VALUES.get(str(weight).strip().lower(), WEIGHT_VALUES["low"])


def high_weight_type_ids(coverage_outline: Any) -> list[str]:
    """Ids of every ``high``-weight reaction type in the outline."""
    return [
        str(rt["id"])
        for rt in reaction_types(coverage_outline)
        if str(rt.get("weight", "")).strip().lower() == "high"
    ]


def _attempts_by_type(attempts_summary: Any) -> dict[str, int]:
    """Normalise a caller ``attempts_summary`` to ``{type_id: graded_attempts}``.

    Accepts either a wrapper dict with an ``attempts_by_type`` mapping or a bare
    ``{type_id: count}`` mapping (metadata keys are ignored). Non-integer counts
    are skipped rather than coerced/fabricated.
    """
    if attempts_summary is None:
        return {}
    if not isinstance(attempts_summary, dict):
        raise TypeError("attempts_summary must be a dict or None")
    if isinstance(attempts_summary.get("attempts_by_type"), dict):
        raw = attempts_summary["attempts_by_type"]
    else:
        raw = {k: v for k, v in attempts_summary.items() if k not in _META_KEYS}
    out: dict[str, int] = {}
    for key, val in raw.items():
        if isinstance(val, bool):  # bool is an int subclass; not a count
            continue
        if isinstance(val, int):
            out[str(key)] = val
        elif isinstance(val, float) and val.is_integer():
            out[str(key)] = int(val)
    return out


def _total_attempts(attempts_summary: Any, counts: dict[str, int]) -> int:
    """Total graded attempts: explicit caller total if given, else sum of counts.

    An explicit total is honoured because some graded attempts may not be
    type-tagged; it is never invented.
    """
    if isinstance(attempts_summary, dict):
        for key in ("total_attempts", "total"):
            val = attempts_summary.get(key)
            if isinstance(val, bool):
                continue
            if isinstance(val, int):
                return val
            if isinstance(val, float) and val.is_integer():
                return int(val)
    return sum(counts.values())


# --- The rule --------------------------------------------------------------
@dataclass(frozen=True)
class GiveUpRule:
    """Give-up thresholds + the abstention decisions they drive.

    Thresholds are fields so they can be adjusted *with a recorded reason*
    (docs/give_up_rule.md) rather than edited inline.
    """

    min_total_attempts: int = MIN_TOTAL_ATTEMPTS
    min_coverage_fraction: float = MIN_COVERAGE_FRACTION
    min_high_weight_attempts: int = MIN_HIGH_WEIGHT_ATTEMPTS
    min_type_attempts: int = MIN_TYPE_ATTEMPTS
    pointer: str = GIVE_UP_RULE_POINTER

    def readiness_gate(
        self, attempts_summary: Any, coverage_outline: Any
    ) -> dict[str, Any]:
        """Enforce the full Readiness rule.

        Returns ``{"abstained": bool, "reasons": [str]}``. When abstaining, each
        reason names the failed condition AND what is still needed (missing
        attempt counts, deficient type ids), e.g.
        ``"volume below threshold: 108/150 graded attempts - need 42 more"`` and
        ``"depth: SN2 has 1/3 attempts - need 2 more"``.
        """
        counts = _attempts_by_type(attempts_summary)
        outline = reaction_types(coverage_outline)
        outline_ids = [str(rt["id"]) for rt in outline]
        n_outline = len(outline_ids)
        total = _total_attempts(attempts_summary, counts)

        reasons: list[str] = []

        # 1. Volume.
        if total < self.min_total_attempts:
            reasons.append(
                f"volume below threshold: {total}/{self.min_total_attempts} "
                f"graded attempts - need {self.min_total_attempts - total} more"
            )

        # 2. Breadth: fraction of the outline with at least one attempt.
        attempted = [tid for tid in outline_ids if counts.get(tid, 0) > 0]
        fraction = (len(attempted) / n_outline) if n_outline else 0.0
        if n_outline == 0 or fraction < self.min_coverage_fraction:
            required = math.ceil(self.min_coverage_fraction * n_outline)
            more = max(0, required - len(attempted))
            reasons.append(
                "breadth below threshold: attempts span "
                f"{len(attempted)}/{n_outline} reaction types "
                f"({_pct(fraction)}) - need "
                f">={_pct(self.min_coverage_fraction)} "
                f"({required}/{n_outline}), {more} more type(s) with an attempt"
            )

        # 3. Depth on every high-weight type.
        for tid in high_weight_type_ids(coverage_outline):
            have = counts.get(tid, 0)
            if have < self.min_high_weight_attempts:
                reasons.append(
                    f"depth: high-weight type {tid} has "
                    f"{have}/{self.min_high_weight_attempts} attempts - "
                    f"need {self.min_high_weight_attempts - have} more"
                )

        return {"abstained": bool(reasons), "reasons": reasons}

    def performance_gate(self, attempt_count: int) -> dict[str, Any]:
        """Per-type Performance gate.

        A reaction type abstains until it has ``min_type_attempts`` graded
        attempts. Returns ``{"abstained": bool, "reasons": [str]}``.
        """
        n = int(attempt_count)
        if n >= self.min_type_attempts:
            return {"abstained": False, "reasons": []}
        return {
            "abstained": True,
            "reasons": [
                f"need {self.min_type_attempts - n} more graded attempt(s) "
                f"({n}/{self.min_type_attempts}) before this type is scored"
            ],
        }


DEFAULT_RULE = GiveUpRule()


def readiness_gate(attempts_summary: Any, coverage_outline: Any) -> dict[str, Any]:
    """Module-level Readiness gate using the default thresholds."""
    return DEFAULT_RULE.readiness_gate(attempts_summary, coverage_outline)


def performance_gate(attempt_count: int) -> dict[str, Any]:
    """Module-level per-type Performance gate using the default thresholds."""
    return DEFAULT_RULE.performance_gate(attempt_count)


def _pct(fraction: float) -> str:
    """Format a fraction as a whole-number percentage for a reason string.

    Display-only rounding of an exact ratio (not a measurement being fudged).
    """
    return f"{round(fraction * 100)}%"
