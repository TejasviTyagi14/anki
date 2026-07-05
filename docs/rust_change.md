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

### Stage 1: mastery-aware review pipeline
1. **`TopicMastery` query — DONE.** Returns, per reaction-type tag (from note
   tags under `mechgrader::reaction::`): total cards, cards with an FSRS memory
   state, mastered-card count, and average recall — computed **inside Rust** over
   the collection, scoped by tag so it stays fast on large collections.
   - *Mastered* (enforced in `rslib/src/mechgrader/mastery.rs`): FSRS
     retrievability ≥ `min_retrievability` (default 0.90) **AND** passing
     mechanism grades (`custom_data.mg_pass`) ≥ `min_pass_grades` (default 2).
   - **Tests:** 5 Rust unit tests (grouping, the two-part mastered gate, the
     average-recall denominator, threshold override, and an
     undo-does-not-break test) + 1 Python end-to-end integration test. All green
     (`make stage1-proof`).
   - Target: fast enough to power the dashboard on a 50,000-card collection
     within the Stage 3 speed budget (dashboard first load p95 < 1s) — measured
     in Stage 3 `make bench`.
2. **`points_at_stake` review ordering — DEFERRED (flag-gated).** An optional
   due-card order sorting by `topic_weight × (1 − topic_mastery)`. It touches the
   scheduler queue/undo, so per the plan we ship `TopicMastery` first (the
   guaranteed real change) and only add ordering if it can be done without undo
   instability.

Required for the real change (status): ≥ 3 Rust unit tests ✓ (5), 1 Python
integration test ✓, an undo-does-not-break test ✓. Android/rsdroid build
confirmation is pending a machine with the Android toolchain (`docs/mobile.md`).

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
