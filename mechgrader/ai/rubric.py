"""The MechGrader mechanism-QUALITY rubric (Stage 2).

Small, explicit, and versioned so every AI judgment can cite a specific rubric
LINE by id. The three criteria are exactly the quality dimensions the AI grader
scores ON TOP OF the deterministic checks:

* ``arrow_pushing``               -- are curved arrows well-formed / balanced?
* ``intermediate_reasonableness`` -- are the intermediates sensible species?
* ``step_ordering``               -- do elementary steps run in a sane order?

Honesty rule (enforced in :mod:`mechgrader.ai.grader_llm`): a judgment that does
not cite a rubric line id from here (plus a reference-mechanism step) earns NO
credit. Line ids are the citation vocabulary -- keep them stable; add new lines
rather than renumbering existing ones.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

__all__ = [
    "RUBRIC_ID",
    "RUBRIC_VERSION",
    "CRITERIA",
    "RUBRIC",
    "criterion_ids",
    "line_ids",
    "lines_for",
    "get_line",
]

RUBRIC_ID = "mechgrader-quality-rubric"
RUBRIC_VERSION = 1

#: The criterion ids scored by the AI grader, in display order.
CRITERIA = ("arrow_pushing", "intermediate_reasonableness", "step_ordering")

#: The rubric itself. ``criteria`` are the scored dimensions; ``lines`` are the
#: citable statements (each tagged with the criterion it belongs to).
RUBRIC: Dict[str, Any] = {
    "id": RUBRIC_ID,
    "version": RUBRIC_VERSION,
    "criteria": [
        {
            "id": "arrow_pushing",
            "title": "Arrow pushing",
            "max_points": 100,
            "description": "Curved arrows are well-formed and electron-balanced.",
        },
        {
            "id": "intermediate_reasonableness",
            "title": "Intermediate reasonableness",
            "max_points": 100,
            "description": "Each intermediate is a chemically reasonable species for the conditions.",
        },
        {
            "id": "step_ordering",
            "title": "Step ordering",
            "max_points": 100,
            "description": "Elementary steps occur in a chemically sensible order.",
        },
    ],
    "lines": [
        {
            "id": "AP1",
            "criterion": "arrow_pushing",
            "text": "Every curved arrow starts at an electron source (a lone pair or a bond) "
            "and ends at an electron sink (an atom or a bond).",
        },
        {
            "id": "AP2",
            "criterion": "arrow_pushing",
            "text": "Arrows conserve electrons and never imply an impossible valence "
            "(e.g. a pentavalent carbon).",
        },
        {
            "id": "AP3",
            "criterion": "arrow_pushing",
            "text": "A step's arrows account for exactly the bonds made and broken between "
            "its reactants and its products.",
        },
        {
            "id": "IR1",
            "criterion": "intermediate_reasonableness",
            "text": "Each intermediate is a plausible species (carbocation, carbanion, radical, "
            "or neutral) for the stated reaction conditions.",
        },
        {
            "id": "IR2",
            "criterion": "intermediate_reasonableness",
            "text": "Formal-charge placement on each intermediate is consistent with the arrows "
            "that formed it.",
        },
        {
            "id": "SO1",
            "criterion": "step_ordering",
            "text": "Steps follow a feasible causal order (bond-breaking and bond-forming happen "
            "in a chemically sensible sequence).",
        },
        {
            "id": "SO2",
            "criterion": "step_ordering",
            "text": "No step consumes a species that has not yet been produced by an earlier step.",
        },
    ],
}


def _rubric(rubric: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return RUBRIC if rubric is None else rubric


def criterion_ids(rubric: Optional[Dict[str, Any]] = None) -> Set[str]:
    """The set of criterion ids defined by ``rubric`` (defaults to :data:`RUBRIC`)."""
    data = _rubric(rubric)
    out: Set[str] = set()
    for crit in data.get("criteria", []):
        if isinstance(crit, dict) and isinstance(crit.get("id"), str):
            out.add(crit["id"])
    return out


def line_ids(rubric: Optional[Dict[str, Any]] = None) -> Set[str]:
    """The set of citable rubric line ids (the citation vocabulary)."""
    data = _rubric(rubric)
    out: Set[str] = set()
    for line in data.get("lines", []):
        if isinstance(line, dict) and isinstance(line.get("id"), str):
            out.add(line["id"])
    return out


def lines_for(criterion: str, rubric: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """All rubric lines tagged with ``criterion``."""
    data = _rubric(rubric)
    return [
        line
        for line in data.get("lines", [])
        if isinstance(line, dict) and line.get("criterion") == criterion
    ]


def get_line(line_id: str, rubric: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Return the rubric line with id ``line_id``, or ``None``."""
    data = _rubric(rubric)
    for line in data.get("lines", []):
        if isinstance(line, dict) and line.get("id") == line_id:
            return line
    return None
