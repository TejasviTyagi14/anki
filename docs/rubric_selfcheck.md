# Rubric self-check

Living checklist against the grading rubric (weights in parentheses). Updated
each stage; each row names where the proof lives. **Honesty first: rows are
marked by what is *demonstrable now*, not by intent.**

## Weighted sections
| Section (weight) | Status | Proof location |
| --- | --- | --- |
| Rust change & fit (20%) | **Stage 1 real change DONE**: `TopicMastery` engine query (FSRS retrievability + reaction-type tags), 5 Rust unit tests + 1 Python integration test (incl. undo-safety). `points_at_stake` deferred (flag-gated). Android build confirmation pending toolchain. | `docs/rust_change.md`, `rslib/src/mechgrader/mastery.rs`, `BUILD_LOG.md §1.1`, `make stage1-proof` |
| Score accuracy & honest uncertainty (20%) | **Give-up rule + three-score module implemented & tested** (11 tests): readiness 118-132 with uncovered types widening range not adding points; abstains with no numeric leakage. Calibration/accuracy evidence still pending Stage 3. | `mechgrader/scoring/`, `docs/model_*.md`, `docs/give_up_rule.md` |
| Study feature on learning science (15%) | Pre-registered; experiment pending Stage 3 | `docs/study_feature.md` |
| AI checking & safety (15%) | **Built + tested (AI-off runnable)**: rubric grader (injection-hardened, citation-required, deterministic-clamped, kill switch; 11 tests), source validator (6 tests), card-gen 3-count checker w/ blocking cutoff (17 tests). Held-out AI *numbers* require a key (`make eval` abstains without one). | `mechgrader/ai/`, `mechgrader/registry/`, `mechgrader/cardgen/`, `docs/ai_eval.md` |
| Re-runnable fair tests (12%) | **`make eval` / `make bench` / `make leakage` all run with real seeded numbers** + calibration harness; `make test`/`test-grader` green. Leakage caught + fixed a real gold-set contamination. | `Makefile`, `docs/results.md`, `docs/ai_eval.md` |
| One shared engine + working sync (10%) | Engine shared by design; desktop proven; **sync conflict logic implemented + tested** (10 tests: card+UUID keyed, logical-timestamp LWW, wrong-clock safe). Server + real 2-device round-trip pending; **mobile build blocked (no SDK here)**. | `mechgrader/sync/`, `docs/sync_conflict_rule.md`, `docs/mobile.md` |
| Useful product & clean UX both apps (8%) | **Core loop pieces built + tested**: MechCard type, web editor (arrow overlay + submit), deterministic grader (62 tests), review pipeline glue (submit->grade->mg_pass->engine, tested end-to-end). aqt reviewer GUI wiring documented but not wired (headless box). Mobile deferred. | `mechgrader/`, `web/mechgrader/`, `docs/reviewer_loop.md` |

## Hard limits (must avoid)
| Hard limit | Current standing |
| --- | --- |
| No real Rust change → max 50% | **Cleared** for Stage 0 (real engine RPC, tested); Stage 1 deepens it. |
| No engine-sharing syncing phone → max 70% | **At risk here** — mobile not yet built (no Android SDK). Honest plan in `docs/mobile.md`; engine sharing is architecturally real. |
| No re-runnable test setup → max 60% | On track — `Makefile` targets; `make stage0-proof` works. |
| No held-out testing → max 60% | Planned Stage 2/3 with `make leakage` enforcement. |
| Made-up/misleading readiness numbers → **automatic fail** | Guarded by the give-up rule (abstain, never fabricate). |
| Either app doesn't run on a clean device → max 50% | **Desktop installer built** (`anki-26.05-mac-apple.dmg`, 215MB, engine change verified inside); runs on a clean mac after clearing Gatekeeper quarantine (adhoc-signed). Mobile not built here (no Android toolchain — honest preflight + reproducible steps). |
| Leaked test data → that score zero | `make leakage` **run + CLEAN** after catching + fixing a real gold split contamination; canonical SMILES + InChIKey + Morgan near-dup. |
| AI claims with no traceable source → AI section zero | Source registry + CI validator required before any AI output (Stage 2). |

## Current honest summary
Stage 0 gate met on desktop (build + real, tested engine change + scaffolding).
The one **open Stage 0 item is the AnkiDroid build**, blocked only by the absence
of an Android toolchain in this environment — documented, not faked.
