"""Source-tracing validator: the honesty gate for MechGrader.

Every MechCard and every AI judgment must resolve to a *named, verifiable
source* in ``sources/registry.json`` (a ``source_ref`` of the form
``"<source_id>#<locator>"``). Anything that cannot be traced back to a
registered source is a **failure**, not a warning: unsourced cards must not
ship, and an AI grade that cites no traceable source zeroes the AI section.

This package does not re-implement source resolution; it reuses
:func:`mechgrader.notetype.mechcard.resolve_source_ref` (the single source of
truth for parsing ``source_ref`` and matching it against the registry) and
turns it into CI-usable checks over whole collections and batches of AI output.

Public API (see :mod:`mechgrader.registry.validator`):

* :func:`validate_source_ref` - validate one ``source_ref``.
* :func:`validate_collection` - scan every MechCard note in a collection.
* :func:`validate_ai_outputs` - scan every AI judgment's cited ``ref``.
* :func:`assert_clean` - raise ``ValueError`` on a failing report (CI gate).
"""

from __future__ import annotations

from .validator import (
    assert_clean,
    validate_ai_outputs,
    validate_collection,
    validate_source_ref,
)

__all__ = [
    "validate_source_ref",
    "validate_collection",
    "validate_ai_outputs",
    "assert_clean",
]
