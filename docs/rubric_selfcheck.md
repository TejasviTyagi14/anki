# Rubric self-check

Living checklist against the grading rubric (weights in parentheses). Updated
each stage; each row names where the proof lives. **Honesty first: rows are
marked by what is *demonstrable now*, not by intent.**

## Weighted sections
| Section (weight) | Status | Proof location |
| --- | --- | --- |
| Rust change & fit (20%) | **Stage 1 real change DONE**: `TopicMastery` engine query (FSRS retrievability + reaction-type tags), 5 Rust unit tests + 1 Python integration test (incl. undo-safety). `points_at_stake` deferred (flag-gated). Android build confirmation pending toolchain. | `docs/rust_change.md`, `rslib/src/mechgrader/mastery.rs`, `BUILD_LOG.md §1.1`, `make stage1-proof` |
| Score accuracy & honest uncertainty (20%) | Models designed + give-up rule fixed; evidence pending Stage 3 | `docs/model_*.md`, `docs/give_up_rule.md` |
| Study feature on learning science (15%) | Pre-registered; experiment pending Stage 3 | `docs/study_feature.md` |
| AI checking & safety (15%) | Designed (sourced/checked/beats-baseline plan + injection hardening); pending Stage 2 | `docs/ai_eval.md`, `sources/registry.json` |
| Re-runnable fair tests (12%) | `Makefile` + seeds plan; `make stage0-proof` real now; eval/bench/leakage pending | `Makefile`, `BUILD_LOG.md` |
| One shared engine + working sync (10%) | Engine shared by design; desktop proven; **mobile build blocked (no SDK here)**; sync pending Stage 2 | `docs/mobile.md`, `docs/sync_conflict_rule.md` |
| Useful product & clean UX both apps (8%) | Prototype exists (`chem-grader/`); integrated loop pending Stage 1 | `chem-grader/README.md`, `mockups/` |

## Hard limits (must avoid)
| Hard limit | Current standing |
| --- | --- |
| No real Rust change → max 50% | **Cleared** for Stage 0 (real engine RPC, tested); Stage 1 deepens it. |
| No engine-sharing syncing phone → max 70% | **At risk here** — mobile not yet built (no Android SDK). Honest plan in `docs/mobile.md`; engine sharing is architecturally real. |
| No re-runnable test setup → max 60% | On track — `Makefile` targets; `make stage0-proof` works. |
| No held-out testing → max 60% | Planned Stage 2/3 with `make leakage` enforcement. |
| Made-up/misleading readiness numbers → **automatic fail** | Guarded by the give-up rule (abstain, never fabricate). |
| Either app doesn't run on a clean device → max 50% | Desktop builds/runs from source; installer in Stage 1; mobile pending. |
| Leaked test data → that score zero | `make leakage` (Stage 3) enforces; gold held-out fraction never fit. |
| AI claims with no traceable source → AI section zero | Source registry + CI validator required before any AI output (Stage 2). |

## Current honest summary
Stage 0 gate met on desktop (build + real, tested engine change + scaffolding).
The one **open Stage 0 item is the AnkiDroid build**, blocked only by the absence
of an Android toolchain in this environment — documented, not faked.
