#!/usr/bin/env python3
"""Tests for the source-tracing validator (the honesty gate).

These prove, end-to-end, that MechGrader genuinely rejects anything that cannot
be traced to a named source in the registry:

* ``validate_source_ref`` accepts a registered id and rejects empty, malformed,
  the ``EXAMPLE-textbook`` placeholder, and unknown ids -- with a clear reason;
* ``validate_collection`` scans a real (temp) Anki collection built from the
  forked ``out/pylib`` engine and flags a card whose ``SourceRef`` was corrupted,
  while passing a collection whose cards all cite resolvable sources;
* ``validate_ai_outputs`` flags each AI judgment whose cited ``ref`` is missing
  or does not resolve; and
* ``assert_clean`` raises on a failing report and is silent on a clean one, so
  it works as a CI gate.

The registry is written to a TEMP file and passed via ``registry_path`` -- the
committed ``sources/registry.json`` is never touched. Cards are created with the
real ``add_mechcard`` (pointed at the temp registry); the "bad" card is made by
corrupting a *created* card's ``SourceRef`` after the fact, since ``add_mechcard``
itself refuses to create an unsourced card.

Run from the repo root:

    PYTHONPATH=out/pylib:. out/pyenv/bin/python mechgrader/tests/test_source_validator.py

(pytest also works: PYTHONPATH=out/pylib:. out/pyenv/bin/python -m pytest \
    mechgrader/tests/test_source_validator.py)
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

from mechgrader.notetype.mechcard import add_mechcard
from mechgrader.registry.validator import (
    assert_clean,
    validate_ai_outputs,
    validate_collection,
    validate_source_ref,
)

TEST_SOURCE_ID = "test-orgo-1ed"


def _new_collection(dir_: str) -> anki.collection.Collection:
    return anki.collection.Collection(os.path.join(dir_, "mech.anki2"))


def _write_temp_registry(path: str, source_id: str = TEST_SOURCE_ID) -> None:
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


def _add_good_mechcard(col, registry_path, *, prompt, source_ref):
    return add_mechcard(
        col,
        prompt=prompt,
        reaction_types=["SN1"],
        reference_mechanism={"steps": []},
        source_ref=source_ref,
        registry_path=registry_path,
    )


def _assert_raises_value_error(fn) -> None:
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("expected ValueError, but none was raised")


def test_validate_source_ref_accepts_registered_and_rejects_bad() -> None:
    with tempfile.TemporaryDirectory() as d:
        registry_path = os.path.join(d, "registry.json")
        _write_temp_registry(registry_path)

        ok, reason = validate_source_ref(
            f"{TEST_SOURCE_ID}#ch15.2", registry_path=registry_path
        )
        assert ok is True, reason
        assert TEST_SOURCE_ID in reason, reason

        # Each of these must be rejected (ok is False) with a non-empty reason.
        bad_cases = ["", "   ", None, "no-hash-locator", f"{TEST_SOURCE_ID}#"]
        for bad in bad_cases:
            ok, reason = validate_source_ref(bad, registry_path=registry_path)
            assert ok is False, (bad, reason)
            assert isinstance(reason, str) and reason, (bad, reason)

        # The placeholder is deliberately non-resolvable, even though it *looks*
        # like a citation -- the most insidious "unsourced" case.
        ok, reason = validate_source_ref(
            "EXAMPLE-textbook#ch1", registry_path=registry_path
        )
        assert ok is False and "placeholder" in reason, reason

        # An id that simply is not in the registry.
        ok, reason = validate_source_ref("nope-9ed#ch1", registry_path=registry_path)
        assert ok is False and "not a registered source" in reason, reason


def test_validate_collection_flags_corrupted_card() -> None:
    with tempfile.TemporaryDirectory() as d:
        col = _new_collection(d)
        registry_path = os.path.join(d, "registry.json")
        _write_temp_registry(registry_path)
        try:
            good = _add_good_mechcard(
                col,
                registry_path,
                prompt="SN1 of tert-butyl bromide + water.",
                source_ref=f"{TEST_SOURCE_ID}#ch15.2",
            )
            bad = _add_good_mechcard(
                col,
                registry_path,
                prompt="E1 of the same substrate.",
                source_ref=f"{TEST_SOURCE_ID}#ch16.1",
            )

            # Corrupt the second card's source to the non-resolvable placeholder,
            # simulating a card that *looks* cited but is not traceable.
            bad_note = col.get_note(bad.id)
            bad_note["SourceRef"] = "EXAMPLE-textbook#ch1"
            col.update_note(bad_note)

            report = validate_collection(col, registry_path=registry_path)

            assert report["ok"] is False, report
            assert report["checked"] == 2, report
            assert len(report["failures"]) == 1, report

            failure = report["failures"][0]
            assert failure["note_id"] == bad.id, (failure, bad.id)
            assert failure["source_ref"] == "EXAMPLE-textbook#ch1", failure
            assert "placeholder" in failure["reason"], failure

            # The good card is NOT reported.
            failing_ids = {f["note_id"] for f in report["failures"]}
            assert good.id not in failing_ids, (good.id, failing_ids)

            # assert_clean must raise on this failing report and name the bad card.
            _assert_raises_value_error(lambda: assert_clean(report))
        finally:
            col.close()


def test_validate_collection_passes_when_all_cards_cite_sources() -> None:
    with tempfile.TemporaryDirectory() as d:
        col = _new_collection(d)
        registry_path = os.path.join(d, "registry.json")
        _write_temp_registry(registry_path)
        try:
            _add_good_mechcard(
                col,
                registry_path,
                prompt="SN1 mechanism.",
                source_ref=f"{TEST_SOURCE_ID}#ch15.2",
            )
            _add_good_mechcard(
                col,
                registry_path,
                prompt="E1 mechanism.",
                source_ref=f"{TEST_SOURCE_ID}#ch16.1",
            )

            report = validate_collection(col, registry_path=registry_path)
            assert report["ok"] is True, report
            assert report["checked"] == 2, report
            assert report["failures"] == [], report
            # Clean report: assert_clean must NOT raise.
            assert_clean(report)
        finally:
            col.close()


def test_validate_ai_outputs_flags_missing_and_unresolvable_refs() -> None:
    with tempfile.TemporaryDirectory() as d:
        registry_path = os.path.join(d, "registry.json")
        _write_temp_registry(registry_path)

        ai_outputs = [
            # 0: resolves -> good
            {"ai": {"source_refs": [
                {"criterion": "leaving group departs", "ref": f"{TEST_SOURCE_ID}#ch15.2"},
            ]}},
            # 1: cites the non-resolvable placeholder -> fail
            {"ai": {"source_refs": [
                {"criterion": "nucleophile attacks", "ref": "EXAMPLE-textbook#ch1"},
            ]}},
            # 2: judgment missing its ref entirely -> fail
            {"ai": {"source_refs": [
                {"criterion": "carbocation forms"},
            ]}},
            # 3: unknown source id -> fail
            {"ai": {"source_refs": [
                {"criterion": "rearrangement", "ref": "nope-9ed#ch3"},
            ]}},
        ]

        report = validate_ai_outputs(ai_outputs, registry_path=registry_path)

        assert report["ok"] is False, report
        assert report["checked"] == 4, report
        assert len(report["failures"]) == 3, report

        failed_criteria = {f["criterion"] for f in report["failures"]}
        assert failed_criteria == {
            "nucleophile attacks",
            "carbocation forms",
            "rearrangement",
        }, failed_criteria
        # The one resolvable judgment is NOT flagged.
        assert "leaving group departs" not in failed_criteria, failed_criteria
        # Every failure records which AI output it came from.
        assert all("output_index" in f for f in report["failures"]), report

        _assert_raises_value_error(lambda: assert_clean(report))


def test_validate_ai_outputs_passes_when_all_refs_resolve() -> None:
    with tempfile.TemporaryDirectory() as d:
        registry_path = os.path.join(d, "registry.json")
        _write_temp_registry(registry_path)

        ai_outputs = [
            {"ai": {"source_refs": [
                {"criterion": "leaving group departs", "ref": f"{TEST_SOURCE_ID}#ch15.2"},
                {"criterion": "nucleophile attacks", "ref": f"{TEST_SOURCE_ID}#ch15.3"},
            ]}},
        ]
        report = validate_ai_outputs(ai_outputs, registry_path=registry_path)
        assert report["ok"] is True, report
        assert report["checked"] == 2, report
        assert report["failures"] == [], report
        assert_clean(report)


def test_assert_clean_raises_on_failure_and_is_silent_when_clean() -> None:
    # Silent on a clean report (returns None, no exception).
    assert assert_clean({"ok": True, "checked": 3, "failures": []}) is None

    # Raises on a failing report, and the message names the offending item.
    failing = {
        "ok": False,
        "checked": 1,
        "failures": [
            {"note_id": 42, "source_ref": "", "reason": "source_ref is empty"}
        ],
    }
    try:
        assert_clean(failing)
    except ValueError as exc:
        message = str(exc)
        assert "FAILED" in message, message
        assert "42" in message, message
    else:
        raise AssertionError("expected assert_clean to raise ValueError")


TESTS = [
    test_validate_source_ref_accepts_registered_and_rejects_bad,
    test_validate_collection_flags_corrupted_card,
    test_validate_collection_passes_when_all_cards_cite_sources,
    test_validate_ai_outputs_flags_missing_and_unresolvable_refs,
    test_validate_ai_outputs_passes_when_all_refs_resolve,
    test_assert_clean_raises_on_failure_and_is_silent_when_clean,
]


def main() -> int:
    for test in TESTS:
        test()
        print(f"ok - {test.__name__}")
    print(f"\nOK: all {len(TESTS)} source-validator tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
