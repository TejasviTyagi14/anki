# The Rust engine change — why it belongs in Rust

MechGrader changes Anki's **Rust engine**, not just the Python/JS screens. This
page explains the change and, per the rubric, *why it must live in Rust*.

## What ships in Rust

All MechGrader backend methods live in a dedicated service,
`MechgraderService` (`proto/anki/mechgrader.proto`,
`rslib/src/mechgrader/`), kept separate from Anki's core services to minimize
the future-merge surface (see `docs/touched_files.md`).

### Stage 0 (done): liveness probe — `MechgraderEngineInfo`
A trivial RPC returning `EngineInfoResponse { info, anki_version, build_hash }`.
Its only job is to prove the `proto → Rust → Python` (and later
`proto → Rust → rsdroid → Kotlin`) pipeline is wired against the *forked* engine,
de-risking the substantive Stage 1 change. Proven by a Rust unit test and an
end-to-end Python `rsbridge` call (see `BUILD_LOG.md`).

### Stage 1 (planned): mastery-aware review pipeline
1. **`TopicMastery` query** — returns, per reaction-type tag (SN1, SN2, E1, E2,
   EAS, carbonyl_addition, …): count of *mastered* cards and average recall,
   computed **inside Rust** over the whole collection.
   - *Mastered* (precise definition, to be enforced in code and documented in
     `docs/model_performance.md`): FSRS retrievability ≥ 0.90 **and** ≥ N
     passing mechanism grades (N default 2) for that card.
   - Target: fast enough to power the dashboard on a 50,000-card collection
     within the Stage 3 speed budget (dashboard first load p95 < 1s).
2. **`points_at_stake` review ordering** — an optional due-card order sorting by
   `topic_weight × (1 − topic_mastery)` so the highest-value weak mechanisms
   surface first, while keeping FSRS intervals valid and undo working. Gated
   behind a flag; if it risks scheduler/undo instability under time pressure,
   `TopicMastery` alone is the guaranteed real change.

Required for Stage 1 (tracked): ≥ 3 Rust unit tests + 1 Python integration test;
an undo-across-the-new-path test proving no collection corruption; and
confirmation the change also builds/passes on the Android/rsdroid build.

## Why this must be in Rust (not Python/JS)

1. **It is the engine's job, and the engine is Rust.** Retrievability/FSRS
   memory state, the card/revlog store, the scheduler queue, and undo all live in
   `rslib`. `TopicMastery` reads FSRS state per card and aggregates by tag;
   `points_at_stake` reorders the *due queue*. Reimplementing these in Python or
   JS would mean re-deriving FSRS state and duplicating scheduler logic outside
   the source of truth — exactly the "don't rewrite the scheduler to avoid
   sharing Rust" anti-pattern the rubric forbids.
2. **One engine, two apps.** Desktop (`rslib`) and Android (`rsdroid` → same
   `rslib`) must produce *identical* numbers offline. Putting the computation in
   Rust means both platforms share one implementation for free; putting it in
   Python (desktop-only) or JS (per-webview) would fork behavior and break the
   "one shared engine" requirement.
3. **Performance on 50k cards.** Aggregating mastery across a 50,000-card
   collection and reordering the due queue must hit tight p95 budgets. This is a
   tight loop over card/revlog rows best done in Rust against the SQLite store,
   not marshalled row-by-row across the Python/JS boundary.
4. **Correctness with undo/transactions.** Any change to review ordering must
   preserve Anki's undo stack and transactional guarantees, which are enforced in
   `rslib`. Doing it there lets us reuse `transact`/undo machinery and *test* that
   undo still works, rather than bolting ordering on top from Python.

## Files
See `docs/touched_files.md` for the exact list and an honest merge-difficulty
assessment.
