# Upstream files touched & future-merge difficulty

An honest accounting of what MechGrader changes in the upstream Anki tree, so a
future rebase onto upstream Anki is predictable. Design goal: **keep new code in
new files; touch upstream files with the smallest possible diffs.**

## Stage 0 (current)

### New files (no merge conflict risk — additive)
| File | Purpose |
| --- | --- |
| `proto/anki/mechgrader.proto` | New `MechgraderService` + `BackendMechgraderService` + `EngineInfoResponse`. |
| `rslib/src/mechgrader/mod.rs` | `impl MechgraderService for Collection` + unit test. |
| `mechgrader/tools/stage0_engine_probe.py` | Re-runnable end-to-end proof. |
| `Makefile`, `THIRD_PARTY_NOTICES.md`, `BUILD_LOG.md`, `docs/*.md`, `sources/registry.json`, `data/**` | Scaffolding. |

### Upstream files edited (all 1-line, additive)
| File | Change | Merge risk |
| --- | --- | --- |
| `rslib/src/lib.rs` | `+ pub mod mechgrader;` (alphabetical) | **Very low** — one line in a sorted module list. |
| `rslib/proto/src/lib.rs` | `+ protobuf!(mechgrader, "mechgrader");` | **Very low** — one line in the proto module list. |
| `rslib/proto/python.rs` | `+ import anki.mechgrader_pb2` in the generated-header list | **Very low** — one line; only needed because a generated Python method references the new pb2 module. |

**Why so small:** MechGrader uses a *dedicated service in its own proto file*
rather than adding RPCs to a core service (e.g. `SchedulerService`). The codegen
requires every `FooService` to have a matching `BackendFooService` (asserted in
`rslib/proto_gen`), so `mechgrader.proto` declares both (the backend one empty).
That keeps all logic in `rslib/src/mechgrader/` and off upstream's hot paths.

## Stage 1 (planned) — expected additional touches
- **New files:** grading, scoring, mechanism-notetype registration, more of
  `rslib/src/mechgrader/` (mastery + ordering + tests), `web/mechgrader/`.
- **Likely small upstream edits:**
  - `proto/anki/mechgrader.proto` — add `TopicMastery*` and ordering messages
    (still our file).
  - Possibly `rslib/src/scheduler/` — to expose a due-card ordering hook for
    `points_at_stake`. This is the **highest merge-risk** item because it touches
    the scheduler queue; it will be kept behind a flag and isolated to the
    smallest hook. If the hook proves invasive, `points_at_stake` is deferred and
    `TopicMastery` (which needs no scheduler edits) remains the guaranteed change.
  - Notetype: the MechCard type is created as data (a notetype in the collection),
    not by editing upstream notetype code where avoidable.

## Overall merge-difficulty assessment
- **Stage 0: trivial.** Three 1-line additive edits + new files. A rebase onto a
  newer upstream Anki would almost certainly apply cleanly.
- **Stage 1: low–moderate.** The only real risk is the optional scheduler
  ordering hook; everything else is additive/new-file. Mitigation: flag-gate the
  scheduler hook and keep it to one call site.
