#!/usr/bin/env python3
"""Stage 1 end-to-end loop test: MechCard -> submit -> grade -> mg_pass ->
the same card is visible to the Rust topic_mastery engine query.

Grading itself (RDKit) is covered by mechgrader/tests/test_deterministic_grader.py;
here we inject a stub grader so the ORCHESTRATION (reading the reference,
recording mg_pass/mg_attempts in custom_data, returning the reveal reference +
a *suggested* FSRS rating, and the counter feeding the engine) is proven in the
Anki Python environment (which has no RDKit).

Run:
    PYTHONPATH=out/pylib:. out/pyenv/bin/python mechgrader/tests/test_reviewer_pipeline.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import anki.collection

from mechgrader.notetype.mechcard import add_mechcard
from mechgrader.reviewer.pipeline import grade_submission

REFERENCE = {
    "steps": [
        {
            "reactants": ["CC(C)(C)Br", "O"],
            "arrows": [{"from": "bond:1-4", "to": "atom:1", "kind": "curved"}],
            "products": ["CC(C)(C)O"],
        }
    ]
}
SUBMISSION = {"steps": [{"reactants": ["CC(C)(C)Br", "O"], "arrows": [], "products": ["CC(C)(C)O"]}]}


class StubGrader:
    """Records what it was called with; returns a canned verdict."""

    def __init__(self, passed: bool, score: int) -> None:
        self.passed = passed
        self.score = score
        self.seen: list = []

    def __call__(self, submitted: dict, reference: dict) -> dict:
        self.seen.append((submitted, reference))
        return {
            "valid": True,
            "passed": self.passed,
            "score": self.score,
            "product_match": self.passed,
            "balance_ok": True,
            "per_step": [],
            "reasons": ["stub grader verdict"],
        }


def _mg(card_custom_data: str) -> dict:
    return json.loads(card_custom_data) if card_custom_data.strip() else {}


def test_review_loop_end_to_end() -> None:
    with tempfile.TemporaryDirectory() as d:
        registry_path = os.path.join(d, "registry.json")
        with open(registry_path, "w") as fh:
            json.dump({"sources": [{"id": "test-src", "title": "Test Source"}]}, fh)

        col = anki.collection.Collection(os.path.join(d, "loop.anki2"))
        try:
            note = add_mechcard(
                col,
                prompt="SN1 of tert-butyl bromide + water. Draw the mechanism.",
                reaction_types=["SN1"],
                reference_mechanism=REFERENCE,
                source_ref="test-src#ch15.2",
                registry_path=registry_path,
            )
            cid = col.find_cards(f"nid:{note.id}")[0]

            # 1) A passing submission increments mg_pass and returns the reveal reference.
            passer = StubGrader(passed=True, score=85)
            r1 = grade_submission(col, cid, SUBMISSION, grader=passer, confidence=0.7, time_ms=42000)
            assert r1["mg_pass"] == 1, r1
            assert r1["mg_attempts"] == 1, r1
            assert r1["reference"] == REFERENCE, "reference must be passed through for reveal"
            assert passer.seen[0][1] == REFERENCE, "grader must receive the card's reference"
            assert r1["suggested_rating"] in ("Good", "Easy"), r1
            assert r1["confidence"] == 0.7 and r1["time_ms"] == 42000  # recorded, not used to inflate

            # 2) A second pass increments again.
            r2 = grade_submission(col, cid, SUBMISSION, grader=StubGrader(True, 92))
            assert r2["mg_pass"] == 2 and r2["mg_attempts"] == 2, r2

            # 3) A failing submission does NOT increment mg_pass (attempts still counts).
            r3 = grade_submission(col, cid, SUBMISSION, grader=StubGrader(False, 30))
            assert r3["mg_pass"] == 2, r3
            assert r3["mg_attempts"] == 3, r3
            assert r3["suggested_rating"] in ("Again", "Hard"), r3

            # 4) Persisted to the card's custom_data (short keys; mg_pass is the
            #    exact key the Rust engine reads).
            data = _mg(col.get_card(cid).custom_data)
            assert data["mg_pass"] == 2 and data["mg_att"] == 3, data

            # 5) The same card is visible to the Rust topic_mastery engine query.
            topics = list(
                col._backend.topic_mastery(
                    search="", tag_prefix="", min_retrievability=0.0, min_pass_grades=0
                )
            )
            by_type = {t.reaction_type: t for t in topics}
            assert "SN1" in by_type, by_type
            assert by_type["SN1"].total_cards == 1, by_type["SN1"]
            print(
                f"loop OK: SN1 total={by_type['SN1'].total_cards} "
                f"mg_pass(persisted)={data['mg_pass']} mg_att={data['mg_att']}"
            )
        finally:
            col.close()


def main() -> int:
    test_review_loop_end_to_end()
    print("\nOK: review loop (submit -> grade -> mg_pass -> engine) proven end-to-end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
