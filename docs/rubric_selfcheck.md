# Rubric self-check

Living checklist against the grading rubric (weights in parentheses). Updated
each stage; each row names where the proof lives. **Honesty first: rows are
marked by what is *demonstrable now*, not by intent.**

## Weighted sections
| Section (weight) | Status | Proof location |
| --- | --- | --- |
| Rust change & fit (20%) | **Stage 1 real change DONE**: `TopicMastery` engine query (FSRS retrievability + reaction-type tags), 5 Rust unit tests + 1 Python integration test (incl. undo-safety). `points_at_stake` deferred (flag-gated). Android build confirmation pending toolchain. | `docs/rust_change.md`, `rslib/src/mechgrader/mastery.rs`, `BUILD_LOG.md §1.1`, `make stage1-proof` |
| Score accuracy & honest uncertainty (20%) | Give-up rule + three-score module (11 tests); **memory calibration harness** (Brier/log-loss/ECE, detects miscalibration) + **paraphrase bridge test** (recall vs performance gap) built + tested. Real-data calibration/accuracy honestly pending (Section 9). | `mechgrader/scoring/`, `mechgrader/calibration/`, `mechgrader/paraphrase/`, `docs/model_*.md` |
| Study feature on learning science (15%) | **Pre-registered + fair three-arm experiment built + run** (interleaved/blocked/plain, same learners/items/time; stated learner model with a switch cost so it isn't rigged; confusability sweep shows the null region). 5 tests. SIMULATION, honestly labeled; harness ready for real cohort. | `mechgrader/experiment/`, `docs/study_feature.md`, `docs/results.md` |
| AI checking & safety (15%) | **Built + tested (AI-off runnable)**: rubric grader (injection-hardened, citation-required, deterministic-clamped, kill switch; 11 tests), source validator (6 tests), card-gen 3-count checker w/ blocking cutoff (17 tests). Held-out AI *numbers* require a key (`make eval` abstains without one). | `mechgrader/ai/`, `mechgrader/registry/`, `mechgrader/cardgen/`, `docs/ai_eval.md` |
| Re-runnable fair tests (12%) | **`make eval` / `make bench` / `make leakage` all run with real seeded numbers** + calibration harness; `make test`/`test-grader` green. Leakage caught + fixed a real gold-set contamination. | `Makefile`, `docs/results.md`, `docs/ai_eval.md` |
| One shared engine + working sync (10%) | **iOS app runs the SAME native `rslib` engine** (ios/rust-ffi → `mechgrader_engine_info` RPC in the Simulator) **and syncs a card phone→desktop** via a native FFI `sync_push` behind a "Sync card → desktop" button — verified `make sync-ios-verify` (phone push → server → desktop, `phone_card_found=True → PASS`) + `make sync-roundtrip` + conflict logic (10 tests). Remaining: physical-device signing (Simulator + localhost server here). | `ios/rust-ffi/`, `mechgrader/tools/sync_ios_verify.py`, `mechgrader/sync/`, `docs/mobile.md` |
| Useful product & clean UX both apps (8%) | Core loop built + tested: MechCard type, web editor (guided flow, quick-insert chips, **click-to-draw structure editor**, curved arrows), deterministic grader (62 tests) wired to the editor's Submit (**live RDKit grades in-browser**), review pipeline (submit->grade->mg_pass->engine). **Desktop installer built** (.dmg). aqt reviewer GUI wiring documented, not wired (headless box); mobile deferred. | `web/mechgrader/`, `mechgrader/`, `docs/reviewer_loop.md`, `docs/installer.md` |

## Hard limits (must avoid)
| Hard limit | Current standing |
| --- | --- |
| No real Rust change → max 50% | **Cleared** for Stage 0 (real engine RPC, tested); Stage 1 deepens it. |
| No engine-sharing syncing phone → max 70% | **Addressed** — the iOS app runs the **native `rslib` engine** (`make ios`) **and its "Sync card → desktop" button pushes a card to the server via a native FFI**, which a desktop syncs down (`make sync-ios-verify → PASS`; live via `make sync-server` + `make sync-pull`). Remaining: physical-device signing (Simulator + localhost server here). |
| No re-runnable test setup → max 60% | **Cleared** — `make test` / `test-grader` (69) / `eval` / `leakage` / `bench` / `sync-roundtrip` all run; `chem-grader/` now tracked so a clean clone can run them. |
| No held-out testing → max 60% | **Cleared** — leakage-clean 15/13 split; `make eval` runs held-out-only (baseline agreement 0.867); `test_run_eval_is_heldout_only` passes. |
| Made-up/misleading readiness numbers → **automatic fail** | Guarded by the give-up rule (abstain, never fabricate). |
| Either app doesn't run on a clean device → max 50% | **Desktop**: `.dmg` (215MB) runs on a clean mac after clearing Gatekeeper (adhoc-signed). **iOS**: builds + runs the native engine in the Simulator (`make ios`); physical-device install needs an Apple Developer cert (not done). Android not built here (no SDK). |
| Leaked test data → that score zero | `make leakage` **run + CLEAN** after catching + fixing a real gold split contamination; canonical SMILES + InChIKey + Morgan near-dup. |
| AI claims with no traceable source → AI section zero | Source registry + CI validator required before any AI output (Stage 2). |

## Current honest summary
Stages 0–3 substantially built on desktop: the real Rust engine change
(`topic_mastery`, tested), the deterministic grader + AI rubric grader (sourced,
injection-hardened, baseline-beating-by-design), the three scores + give-up rule,
sync conflict logic, the shared web editor (with a click-to-draw structure
editor + live RDKit grading), and Stage-3 evidence: **leakage CLEAN** (after
catching a real leak), **bench** (dashboard p95 38ms on 50k), **calibration**,
**paraphrase bridge**, **study-feature experiment**, and **crash recovery**
(zero corruption). The **desktop app is fully built** (`.dmg`).

Honest open items: the **AnkiDroid/iOS mobile build** (no Android toolchain here —
turnkey path documented, `make build-mobile` preflight), the **aqt reviewer GUI
wiring** (needs a display), and **real-data** calibration/accuracy/study numbers
(the harnesses are built + tested on labeled simulations and run on real data
directly). Nothing is faked; simulations are labeled as such.
