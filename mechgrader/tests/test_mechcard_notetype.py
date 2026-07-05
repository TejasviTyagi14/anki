#!/usr/bin/env python3
"""Tests for the MechCard note type and its source-registry guardrails.

These prove, end-to-end against a real (temp) Anki collection built from the
forked ``out/pylib`` engine, that:

* ``ensure_mechcard_notetype`` is idempotent (same id, no duplicate note type);
* ``add_mechcard`` writes the expected fields, round-trips the reference
  mechanism through JSON, and tags the note ``mechgrader::reaction::<type>`` so
  the Rust ``topic_mastery`` query can attribute it; and
* both an empty ``source_ref`` and an unresolvable one are rejected with
  ``ValueError`` (the ``EXAMPLE-textbook`` placeholder included), so no card can
  ship without a verifiable source.

The registry is written to a TEMP file and passed via ``registry_path`` — the
committed ``sources/registry.json`` is never touched.

Run from the repo root:

    PYTHONPATH=out/pylib out/pyenv/bin/python mechgrader/tests/test_mechcard_notetype.py

(pytest also works: PYTHONPATH=out/pylib out/pyenv/bin/python -m pytest \
    mechgrader/tests/test_mechcard_notetype.py)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

# Make the repo root importable so ``mechgrader.*`` resolves whether this file is
# run directly as a script or under pytest. ``anki`` continues to resolve via
# PYTHONPATH=out/pylib (+ the dev venv); the repo root exposes no ``anki`` package
# so there is no shadowing.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import anki.collection

from mechgrader.notetype.mechcard import (
    MECHCARD_FIELDS,
    MECHCARD_NOTETYPE_NAME,
    REACTION_TAG_PREFIX,
    add_mechcard,
    ensure_mechcard_notetype,
    resolve_source_ref,
)


def _new_collection(dir_: str) -> anki.collection.Collection:
    return anki.collection.Collection(os.path.join(dir_, "mech.anki2"))


def _count_notetypes_named(col: anki.collection.Collection, name: str) -> int:
    return sum(1 for nt in col.models.all_names_and_ids() if nt.name == name)


def _write_temp_registry(path: str, source_id: str) -> None:
    """Write a minimal registry with one real test source id (never the placeholder)."""
    registry = {
        "schema_version": 1,
        "sources": [
            {
                "id": source_id,
                "type": "textbook",
                "title": "Test Organic Chemistry (1ed)",
                "authors": ["Tester"],
                "year": 2024,
            }
        ],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(registry, handle)


def _assert_raises_value_error(fn) -> None:
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("expected ValueError, but none was raised")


def test_ensure_notetype_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as d:
        col = _new_collection(d)
        try:
            id1 = ensure_mechcard_notetype(col)
            id2 = ensure_mechcard_notetype(col)

            assert id1 == id2, (id1, id2)
            assert _count_notetypes_named(col, MECHCARD_NOTETYPE_NAME) == 1

            notetype = col.models.get(id1)
            assert col.models.field_names(notetype) == list(MECHCARD_FIELDS)
            # Front renders the prompt; back exposes the (empty) canvas mount point.
            assert "{{Prompt}}" in notetype["tmpls"][0]["qfmt"]
            assert 'id="mechgrader-canvas"' in notetype["tmpls"][0]["afmt"]
        finally:
            col.close()


def test_add_mechcard_persists_fields_tags_and_reference() -> None:
    with tempfile.TemporaryDirectory() as d:
        col = _new_collection(d)
        registry_path = os.path.join(d, "registry.json")
        _write_temp_registry(registry_path, "test-orgo-1ed")
        try:
            mechanism = {
                "steps": [
                    {"type": "bond_break", "atoms": [1, 2]},
                    {"type": "bond_form", "atoms": [2, 3]},
                ],
                "arrows": 2,
                # include a quote to prove JSON survives the notetype round-trip
                "note": 'water attacks the "carbocation"',
            }
            note = add_mechcard(
                col,
                prompt="SN1 of tert-butyl bromide + water. Draw the mechanism.",
                reaction_types=["SN1"],
                reference_mechanism=mechanism,
                source_ref="test-orgo-1ed#ch15.2",
                registry_path=registry_path,
            )

            # Reload from the DB to assert what actually persisted.
            reloaded = col.get_note(note.id)
            assert reloaded["Prompt"].startswith("SN1 of tert-butyl bromide")
            assert reloaded["SourceRef"] == "test-orgo-1ed#ch15.2"
            assert reloaded["ReactionTypeTags"] == "SN1"
            assert json.loads(reloaded["ReferenceMechanism"]) == mechanism

            assert reloaded.has_tag(f"{REACTION_TAG_PREFIX}SN1")
            assert f"{REACTION_TAG_PREFIX}SN1" in reloaded.tags
            # The single template yields exactly one card.
            assert len(reloaded.cards()) == 1
        finally:
            col.close()


def test_add_mechcard_tags_every_reaction_type() -> None:
    with tempfile.TemporaryDirectory() as d:
        col = _new_collection(d)
        registry_path = os.path.join(d, "registry.json")
        _write_temp_registry(registry_path, "test-orgo-1ed")
        try:
            note = add_mechcard(
                col,
                prompt="Contrast the SN1 and E1 pathways for this substrate.",
                reaction_types=["SN1", "E1"],
                reference_mechanism={"pathways": ["SN1", "E1"]},
                source_ref="test-orgo-1ed#ch17.1",
                registry_path=registry_path,
            )
            reloaded = col.get_note(note.id)
            assert reloaded.has_tag(f"{REACTION_TAG_PREFIX}SN1")
            assert reloaded.has_tag(f"{REACTION_TAG_PREFIX}E1")
            assert reloaded["ReactionTypeTags"] == "SN1 E1"
        finally:
            col.close()


def test_resolver_finds_real_ids_but_rejects_placeholder_and_malformed() -> None:
    with tempfile.TemporaryDirectory() as d:
        registry_path = os.path.join(d, "registry.json")
        _write_temp_registry(registry_path, "test-orgo-1ed")

        resolved = resolve_source_ref(
            "test-orgo-1ed#ch15.2", registry_path=registry_path
        )
        assert resolved is not None and resolved["id"] == "test-orgo-1ed"

        # Placeholder is never resolvable, even when it appears in the registry.
        assert (
            resolve_source_ref("EXAMPLE-textbook#ch1", registry_path=registry_path)
            is None
        )
        # Unknown id and malformed refs.
        assert resolve_source_ref("nope-9ed#ch1", registry_path=registry_path) is None
        assert resolve_source_ref("", registry_path=registry_path) is None
        assert resolve_source_ref("no-hash-locator", registry_path=registry_path) is None
        assert resolve_source_ref("test-orgo-1ed#", registry_path=registry_path) is None


def test_add_mechcard_rejects_empty_and_unresolvable_source_refs() -> None:
    with tempfile.TemporaryDirectory() as d:
        col = _new_collection(d)
        registry_path = os.path.join(d, "registry.json")
        _write_temp_registry(registry_path, "test-orgo-1ed")
        try:
            def add(source_ref: str):
                return lambda: add_mechcard(
                    col,
                    prompt="x",
                    reaction_types=["SN1"],
                    reference_mechanism={},
                    source_ref=source_ref,
                    registry_path=registry_path,
                )

            _assert_raises_value_error(add(""))  # empty
            _assert_raises_value_error(add("   "))  # whitespace-only
            _assert_raises_value_error(add("does-not-exist#ch1"))  # unknown id
            _assert_raises_value_error(add("EXAMPLE-textbook#ch1"))  # placeholder

            # None of the rejected attempts created a note.
            assert col.note_count() == 0
        finally:
            col.close()


TESTS = [
    test_ensure_notetype_is_idempotent,
    test_add_mechcard_persists_fields_tags_and_reference,
    test_add_mechcard_tags_every_reaction_type,
    test_resolver_finds_real_ids_but_rejects_placeholder_and_malformed,
    test_add_mechcard_rejects_empty_and_unresolvable_source_refs,
]


def main() -> int:
    for test in TESTS:
        test()
        print(f"ok - {test.__name__}")
    print(f"\nOK: all {len(TESTS)} MechCard note-type tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
