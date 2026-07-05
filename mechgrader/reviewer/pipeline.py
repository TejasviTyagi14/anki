"""The submit -> grade -> record step of the review loop.

`grade_submission` is deliberately grader-agnostic: it takes a `grader`
callable so the orchestration (reading the reference, grading, updating the
per-card `mg_pass` counter that the Rust `topic_mastery` query reads, returning
the traceable breakdown + reference for the side-by-side reveal) can be tested in
the Anki Python environment without RDKit installed. In the app, the default
grader is the deterministic RDKit grader; the webview additionally has the
RDKit-JS mirror for offline grading.

Model separation is preserved: this updates only the mechanism-performance
signal (`mg_pass`). The FSRS memory rating (Again/Hard/Good/Easy) is a SEPARATE
signal the student confirms — we only *suggest* one from the grade.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

# (submitted_mechanism, reference_mechanism) -> grade dict with at least
# {"passed": bool, "score": int, "valid": bool}. See mechgrader.grading.
GraderFn = Callable[[dict, dict], dict]

REFERENCE_FIELD = "ReferenceMechanism"


def _default_grader(submitted: dict, reference: dict) -> dict:
    # Imported lazily so this module is importable without RDKit (the RDKit
    # grader lives behind chem-grader and is exercised by its own test suite).
    from mechgrader.grading.deterministic import grade_mechanism

    return grade_mechanism(submitted, reference)


def _suggest_rating(grade: dict) -> str:
    """Suggest an FSRS rating from the mechanism grade. The student CONFIRMS it;
    the grade never silently sets memory scheduling (models stay separate)."""
    if not grade.get("valid", True):
        return "Again"
    score = int(grade.get("score", 0))
    if not grade.get("passed"):
        return "Again" if score < 50 else "Hard"
    return "Good" if score < 90 else "Easy"


def grade_submission(
    col: Any,
    card_id: Any,
    submitted_mechanism: dict,
    *,
    grader: Optional[GraderFn] = None,
    confidence: Optional[float] = None,
    hints_used: int = 0,
    time_ms: Optional[int] = None,
) -> dict:
    """Grade a drawn mechanism for a MechCard and record the result.

    Returns a dict with the traceable grade breakdown, the updated per-card
    mechanism-pass counters, the reference mechanism (for the side-by-side
    reveal), the calibration inputs (confidence/hints/time — recorded, never
    used to inflate the grade), and a *suggested* (not applied) FSRS rating.
    """
    grader = grader or _default_grader
    card = col.get_card(card_id)
    note = card.note()

    try:
        reference_raw = note[REFERENCE_FIELD]
    except (KeyError, IndexError) as exc:
        raise ValueError(
            f"card {card_id} is not a MechCard (no {REFERENCE_FIELD!r} field)"
        ) from exc
    reference = json.loads(reference_raw) if reference_raw.strip() else {"steps": []}

    grade = grader(submitted_mechanism, reference)

    # Per-card counters in custom_data. Anki caps custom_data keys at 8 bytes,
    # so keys are short. `mg_pass` (7 bytes) is exactly what the Rust
    # topic_mastery query reads to decide mastery; `mg_att` is the honest
    # attempt denominator; `mg_sc`/`mg_ms` are the last score / time taken.
    data = json.loads(card.custom_data) if card.custom_data.strip() else {}
    data["mg_att"] = int(data.get("mg_att", 0)) + 1
    if grade.get("passed"):
        data["mg_pass"] = int(data.get("mg_pass", 0)) + 1
    data["mg_sc"] = int(grade.get("score", 0))
    if time_ms is not None:
        data["mg_ms"] = int(time_ms)
    card.custom_data = json.dumps(data, separators=(",", ":"))
    col.update_card(card)

    return {
        "grade": grade,
        "mg_pass": int(data.get("mg_pass", 0)),
        "mg_attempts": int(data["mg_att"]),
        "reference": reference,
        # calibration inputs — stored/returned for the performance model,
        # explicitly NOT used to change the grade.
        "confidence": confidence,
        "hints_used": int(hints_used),
        "time_ms": time_ms,
        "suggested_rating": _suggest_rating(grade),
    }
