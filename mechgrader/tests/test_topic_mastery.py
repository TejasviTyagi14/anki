#!/usr/bin/env python3
"""Stage 1 Python integration test: call the new Rust ``TopicMastery`` RPC
end-to-end through the ``_rsbridge`` FFI, proving the mastery-aware review
pipeline surfaces from the forked engine to Python exactly as the desktop app
(and, once rsdroid is rebuilt, the Android app) would call it.

The mastered/retrievability/pass-count logic is exhaustively covered by the Rust
unit tests in ``rslib/src/mechgrader/mastery.rs``; this test proves the RPC is
reachable and returns correctly-grouped structured data end-to-end.

Run from the repo root:

    PYTHONPATH=out/pylib out/pyenv/bin/python mechgrader/tests/test_topic_mastery.py
"""

from __future__ import annotations

import os
import tempfile

import anki.collection


def _add_card(col: anki.collection.Collection, tags: list[str]) -> None:
    note = col.new_note(col.models.by_name("Basic"))
    note.tags = list(tags)
    note["Front"] = "SN1 of tert-butyl bromide + water. Draw the mechanism."
    note["Back"] = "reference"
    col.add_note(note, col.decks.id("Default"))


def test_topic_mastery_groups_by_reaction_tag() -> None:
    with tempfile.TemporaryDirectory() as d:
        col = anki.collection.Collection(os.path.join(d, "s1.anki2"))
        try:
            _add_card(col, ["mechgrader::reaction::SN1"])
            _add_card(col, ["mechgrader::reaction::SN1"])
            _add_card(col, ["mechgrader::reaction::SN2"])
            _add_card(col, ["unrelated::tag"])  # must be ignored

            topics = list(
                col._backend.topic_mastery(
                    search="", tag_prefix="", min_retrievability=0.0, min_pass_grades=0
                )
            )
            by_type = {t.reaction_type: t for t in topics}
            for name in sorted(by_type):
                t = by_type[name]
                print(
                    f"{name}: total={t.total_cards} with_memory={t.cards_with_memory} "
                    f"mastered={t.mastered_cards} avg_recall={t.average_recall:.3f}"
                )

            assert set(by_type) == {"SN1", "SN2"}, sorted(by_type)
            assert by_type["SN1"].total_cards == 2
            assert by_type["SN2"].total_cards == 1
            # No mechanism grades / memory yet -> nothing mastered, honest zeros.
            assert by_type["SN1"].mastered_cards == 0
            assert by_type["SN1"].cards_with_memory == 0
        finally:
            col.close()


def main() -> int:
    test_topic_mastery_groups_by_reaction_tag()
    print("\nOK: Rust TopicMastery RPC reachable from Python via rsbridge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
