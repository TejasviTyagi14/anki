"""Enforce: every card and every AI judgment resolves to a named source.

This module is deliberately thin. The authority on whether a ``source_ref``
resolves is :func:`mechgrader.notetype.mechcard.resolve_source_ref`; we import
and reuse it rather than re-loading or re-matching the registry ourselves. What
this module adds is *enforcement surface*:

* a boolean+reason wrapper (:func:`validate_source_ref`),
* a whole-collection scan of MechCard notes (:func:`validate_collection`),
* a whole-batch scan of AI judgments (:func:`validate_ai_outputs`), and
* a CI gate that turns a failing report into an exception
  (:func:`assert_clean`).

Report schema
-------------
:func:`validate_collection` and :func:`validate_ai_outputs` both return::

    {
      "ok": bool,          # True  iff there are no failures
      "checked": int,      # how many items were examined
      "failures": [ ... ], # one dict per unresolved / unsourced item
    }

For a collection each failure is
``{"note_id": int, "source_ref": str, "reason": str}``; for AI outputs each
failure is ``{"output_index": int, "criterion": str | None, "ref": str,
"reason": str}``. ``ok`` is ``True`` only when ``failures`` is empty, so a
report is safe to feed straight into :func:`assert_clean`.

Honesty note: these checks never "pass by default". An empty/missing
``source_ref`` and an unknown ``source_id`` both fail, and the intentionally
non-resolvable ``EXAMPLE-textbook`` placeholder fails too.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from mechgrader.notetype.mechcard import (
    MECHCARD_NOTETYPE_NAME,
    PLACEHOLDER_SOURCE_ID,
    resolve_source_ref,
)

if TYPE_CHECKING:
    from anki.collection import Collection

__all__ = [
    "validate_source_ref",
    "validate_collection",
    "validate_ai_outputs",
    "assert_clean",
]

#: Field on a MechCard note holding its ``"<source_id>#<locator>"`` citation.
SOURCE_REF_FIELD = "SourceRef"


def _explain_unresolvable(source_ref: Any) -> str:
    """Human-readable reason a ``source_ref`` did not resolve.

    This is *message-only*: the pass/fail decision is made solely by
    :func:`resolve_source_ref`. We inspect the shape of the (already-rejected)
    ref just to say *why* it looks wrong, so a CI failure points at the actual
    problem instead of a generic "did not resolve".
    """
    if source_ref is None:
        return "source_ref is missing (None); every card/judgment must cite a source"
    if not isinstance(source_ref, str):
        return (
            f"source_ref must be a string of the form '<source_id>#<locator>', "
            f"got {type(source_ref).__name__}"
        )
    ref = source_ref.strip()
    if not ref:
        return "source_ref is empty; every card/judgment must cite a source"
    if "#" not in ref:
        return (
            f"malformed source_ref {source_ref!r}: expected '<source_id>#<locator>' "
            "(no '#' found)"
        )
    source_id, _, locator = ref.partition("#")
    source_id, locator = source_id.strip(), locator.strip()
    if not source_id or not locator:
        return (
            f"malformed source_ref {source_ref!r}: both a '<source_id>' and a "
            "'<locator>' are required"
        )
    if source_id == PLACEHOLDER_SOURCE_ID:
        return (
            f"source_id {source_id!r} is the non-resolvable placeholder; replace it "
            "with a real, registered source before shipping"
        )
    return (
        f"source_id {source_id!r} is not a registered source in the registry "
        "(add it to sources/registry.json or fix the citation)"
    )


def validate_source_ref(
    source_ref: Any, registry_path: str | Path | None = None
) -> tuple[bool, str]:
    """Validate a single ``source_ref``; return ``(ok, reason)``.

    Thin wrapper over :func:`resolve_source_ref`: ``ok`` is ``True`` iff the ref
    resolves to a registered, verifiable source. On success ``reason`` names the
    resolved source id; on failure it explains what is wrong (empty, malformed,
    the ``EXAMPLE-textbook`` placeholder, or an unknown id).
    """
    resolved = resolve_source_ref(source_ref, registry_path=registry_path)
    if resolved is not None:
        return True, f"resolved to source {resolved.get('id')!r}"
    return False, _explain_unresolvable(source_ref)


def validate_collection(
    col: Collection, *, registry_path: str | Path | None = None
) -> dict[str, Any]:
    """Scan every MechCard note in ``col`` for a resolvable ``SourceRef``.

    Finds notes by the MechCard note type (by model id, so a missing note type
    simply yields nothing to check rather than erroring), reads each note's
    ``SourceRef`` field and validates it. Returns a report (see module docstring)
    whose ``failures`` name each note whose source is empty or unresolvable.
    """
    failures: list[dict[str, Any]] = []
    checked = 0

    notetype_id = col.models.id_for_name(MECHCARD_NOTETYPE_NAME)
    note_ids = col.find_notes(f"mid:{notetype_id}") if notetype_id is not None else []

    for note_id in note_ids:
        note = col.get_note(note_id)
        checked += 1
        # Guard the field read: a MechCard always has SourceRef, but if the
        # schema were tampered with we must fail loudly, not skip the card.
        source_ref = note[SOURCE_REF_FIELD] if SOURCE_REF_FIELD in note else ""
        ok, reason = validate_source_ref(source_ref, registry_path=registry_path)
        if not ok:
            failures.append(
                {
                    "note_id": int(note_id),
                    "source_ref": source_ref,
                    "reason": reason,
                }
            )

    return {"ok": not failures, "checked": checked, "failures": failures}


def _iter_source_refs(grade: Any) -> list[dict[str, Any]]:
    """Return the ``ai.source_refs`` entries of one AI grade dict (or ``[]``)."""
    if not isinstance(grade, dict):
        return []
    ai = grade.get("ai")
    if not isinstance(ai, dict):
        return []
    refs = ai.get("source_refs")
    if not isinstance(refs, list):
        return []
    return refs


def validate_ai_outputs(
    ai_outputs: list[dict[str, Any]], *, registry_path: str | Path | None = None
) -> dict[str, Any]:
    """Validate the source citations of a batch of AI grades.

    ``ai_outputs`` is a list of AI grade dicts; each may carry
    ``ai.source_refs`` -- a list of ``{"criterion": ..., "ref": ...}`` judgments.
    Every judgment's ``ref`` must resolve; a judgment missing its ``ref`` or
    citing an unresolvable one is a failure. Returns a report (see module
    docstring) whose ``failures`` name each offending judgment.
    """
    failures: list[dict[str, Any]] = []
    checked = 0

    for output_index, grade in enumerate(ai_outputs or []):
        for entry in _iter_source_refs(grade):
            checked += 1
            if isinstance(entry, dict):
                criterion = entry.get("criterion")
                ref = entry.get("ref", "")
            else:
                # Malformed judgment (not a dict): no traceable ref at all.
                criterion = None
                ref = ""
            ok, reason = validate_source_ref(ref, registry_path=registry_path)
            if not ok:
                failures.append(
                    {
                        "output_index": output_index,
                        "criterion": criterion,
                        "ref": ref,
                        "reason": reason,
                    }
                )

    return {"ok": not failures, "checked": checked, "failures": failures}


def _format_failure(failure: dict[str, Any]) -> str:
    """One-line description of a failure from either report type."""
    reason = failure.get("reason", "unresolvable source")
    if "note_id" in failure:
        return (
            f"  - note {failure['note_id']} "
            f"(SourceRef={failure.get('source_ref')!r}): {reason}"
        )
    criterion = failure.get("criterion")
    where = f"AI output #{failure.get('output_index')}"
    if criterion is not None:
        where += f" criterion {criterion!r}"
    return f"  - {where} (ref={failure.get('ref')!r}): {reason}"


def assert_clean(report: dict[str, Any]) -> None:
    """Raise ``ValueError`` if ``report`` has any failure; else return quietly.

    Intended as a CI gate: the build must fail if any card or AI output lacks a
    resolvable source. The message lists every offending item and its reason.
    """
    if report.get("ok"):
        return
    failures = report.get("failures", [])
    lines = "\n".join(_format_failure(f) for f in failures)
    raise ValueError(
        f"source validation FAILED: {len(failures)} of {report.get('checked', 0)} "
        "checked item(s) do not resolve to a registered, verifiable source.\n"
        "Every card and every AI judgment must cite a named source in "
        "sources/registry.json, or it is rejected.\n"
        f"{lines}"
    )
