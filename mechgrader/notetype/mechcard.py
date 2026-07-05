"""The MechCard note/card type and its source-registry guardrails.

A *MechCard* is one organic-chemistry mechanism prompt. Three invariants make
the rest of MechGrader honest, so they are enforced here at creation time:

* **Reaction attribution lives in tags.** Each card is tagged
  ``mechgrader::reaction::<type>`` (one per reaction type). The forked Rust
  engine's ``topic_mastery`` query aggregates per reaction type by reading
  exactly these tags, so ``add_mechcard`` is the single writer that guarantees
  the tag namespace matches what the engine reads.
* **Every card cites a verifiable source.** ``add_mechcard`` refuses to create a
  card whose ``source_ref`` is empty or does not resolve against the source
  registry (``sources/registry.json``). The ``EXAMPLE-textbook`` placeholder in
  that registry is deliberately treated as non-resolvable.
* **The reference mechanism is structured data.** It is stored as a JSON string
  in the ``ReferenceMechanism`` field so the (separately built) web editor and
  the grader can round-trip it.

This module only defines the note type and the safe add/resolve helpers. It does
NOT build the web editor bundle; the back template merely leaves a clearly
marked ``#mechgrader-canvas`` mount point for that separate module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from anki.models import NotetypeId

if TYPE_CHECKING:
    from anki.collection import Collection
    from anki.notes import Note

# Note type identity / schema.
MECHCARD_NOTETYPE_NAME = "MechCard"
MECHCARD_TEMPLATE_NAME = "MechCard"
#: Field order matters: ``Prompt`` (index 0) is the sort/browser field.
MECHCARD_FIELDS: tuple[str, ...] = (
    "Prompt",
    "ReactionTypeTags",
    "ReferenceMechanism",
    "SourceRef",
)

#: Tag namespace the Rust ``topic_mastery`` query reads to attribute a card to a
#: reaction type (see ``rslib/src/mechgrader/mastery.rs``). Must stay in sync.
REACTION_TAG_PREFIX = "mechgrader::reaction::"

#: DOM id of the container the shared web editor mounts into on the card back.
MECHGRADER_CANVAS_ID = "mechgrader-canvas"

#: Placeholder id shipped in the registry; intentionally NOT resolvable so no
#: real card can cite it.
PLACEHOLDER_SOURCE_ID = "EXAMPLE-textbook"

#: Default registry location, anchored to the repo root so it resolves
#: regardless of the current working directory. Tests override via
#: ``registry_path``.
DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "sources" / "registry.json"


FRONT_TEMPLATE = """\
<div class="mechgrader-card mechgrader-front">
  <div class="mechgrader-prompt">{{Prompt}}</div>
</div>
"""

# NOTE: not an f-string — the ``{{Field}}`` markers are Anki template syntax.
BACK_TEMPLATE = """\
{{FrontSide}}

<hr id="answer">

<!-- ===================================================================
     MechGrader web-editor MOUNT POINT.

     The interactive mechanism editor/grader is a SEPARATE web bundle,
     built in its own module (NOT here, and NOT inlined below). At review
     time that bundle mounts into the #mechgrader-canvas element and reads:
       * the reference mechanism from the <script type="application/json">
         payload below (JSON, so it is kept out of HTML attributes), and
       * the source_ref / reaction types from the data-* attributes.
     Do NOT rename or remove #mechgrader-canvas.
     =================================================================== -->
<div class="mechgrader-card mechgrader-back">
  <div class="mechgrader-prompt">{{Prompt}}</div>

  <div id="mechgrader-canvas"
       class="mechgrader-canvas"
       data-source-ref="{{SourceRef}}"
       data-reaction-types="{{ReactionTypeTags}}">
    <!-- MechGrader web editor is injected here by the separate web module. -->
  </div>

  <script id="mechgrader-reference-mechanism" type="application/json">{{ReferenceMechanism}}</script>
</div>
"""

MECHCARD_CSS = """\
.card {
  font-family: arial, sans-serif;
  font-size: 20px;
  text-align: center;
  color: #202020;
  background-color: #ffffff;
}

.mechgrader-prompt {
  font-size: 22px;
  line-height: 1.4;
  margin: 0 auto 1em;
  max-width: 40em;
}

#mechgrader-canvas {
  min-height: 320px;
  margin: 1em auto 0;
  max-width: 40em;
  border: 1px solid #d0d0d0;
  border-radius: 8px;
  background: #fafafa;
}
"""


def ensure_mechcard_notetype(col: Collection) -> NotetypeId:
    """Return the id of the ``MechCard`` note type, creating it if absent.

    Idempotent: if a note type named ``MechCard`` already exists its id is
    returned unchanged and no duplicate is created.
    """
    existing = col.models.id_for_name(MECHCARD_NOTETYPE_NAME)
    if existing is not None:
        return existing

    notetype = col.models.new(MECHCARD_NOTETYPE_NAME)
    for field_name in MECHCARD_FIELDS:
        col.models.add_field(notetype, col.models.new_field(field_name))
    # Prompt (index 0) is the sort field shown in the browser.
    col.models.set_sort_index(notetype, 0)

    template = col.models.new_template(MECHCARD_TEMPLATE_NAME)
    template["qfmt"] = FRONT_TEMPLATE
    template["afmt"] = BACK_TEMPLATE
    col.models.add_template(notetype, template)

    notetype["css"] = MECHCARD_CSS

    col.models.add(notetype)
    return NotetypeId(notetype["id"])


def _load_registry(registry_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(registry_path) if registry_path is not None else DEFAULT_REGISTRY_PATH
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def resolve_source_ref(
    source_ref: str, registry_path: str | Path | None = None
) -> dict[str, Any] | None:
    """Resolve ``"<source_id>#<locator>"`` to its registry entry, or ``None``.

    Returns the matched source dict when ``source_id`` exists in the registry's
    ``sources`` list, otherwise ``None``. The ``EXAMPLE-textbook`` placeholder is
    always treated as non-resolvable. ``registry_path`` lets callers (and tests)
    point at an alternate registry; it defaults to ``sources/registry.json``.
    """
    if not source_ref or "#" not in source_ref:
        return None
    source_id, _, locator = source_ref.partition("#")
    source_id = source_id.strip()
    locator = locator.strip()
    # The format is "<source_id>#<locator>"; both parts are required for a
    # citation to point at a specific, verifiable location.
    if not source_id or not locator:
        return None
    if source_id == PLACEHOLDER_SOURCE_ID:
        return None

    registry = _load_registry(registry_path)
    for source in registry.get("sources", []):
        if isinstance(source, dict) and source.get("id") == source_id:
            return source
    return None


def add_mechcard(
    col: Collection,
    *,
    prompt: str,
    reaction_types: list[str],
    reference_mechanism: dict[str, Any],
    source_ref: str,
    deck_name: str = "Default",
    registry_path: str | Path | None = None,
) -> Note:
    """Create and persist a MechCard note.

    Tags the note ``mechgrader::reaction::<type>`` for each reaction type, stores
    ``json.dumps(reference_mechanism)`` in ``ReferenceMechanism`` and ``source_ref``
    in ``SourceRef``.

    Raises ``ValueError`` if ``source_ref`` is empty or does not resolve via
    :func:`resolve_source_ref` (which rejects the ``EXAMPLE-textbook`` placeholder).
    """
    if not source_ref or not source_ref.strip():
        raise ValueError(
            "MechCard requires a non-empty source_ref: every card must cite a "
            "verifiable source from the registry."
        )
    if resolve_source_ref(source_ref, registry_path=registry_path) is None:
        raise ValueError(
            f"source_ref {source_ref!r} does not resolve to a registered, "
            f"verifiable source (the {PLACEHOLDER_SOURCE_ID!r} placeholder is "
            "intentionally rejected)."
        )

    notetype_id = ensure_mechcard_notetype(col)
    notetype = col.models.get(notetype_id)
    note = col.new_note(notetype)
    note["Prompt"] = prompt
    note["ReactionTypeTags"] = " ".join(reaction_types)
    note["ReferenceMechanism"] = json.dumps(reference_mechanism)
    note["SourceRef"] = source_ref
    note.tags = [f"{REACTION_TAG_PREFIX}{reaction_type}" for reaction_type in reaction_types]

    deck_id = col.decks.id(deck_name)
    col.add_note(note, deck_id)
    return note
