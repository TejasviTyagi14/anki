# MechGrader — Submission index

One page that points to every hand-in artifact and the command that reproduces
each claim. **Honesty first:** rows say what is *demonstrable now*, and gaps are
labeled, not hidden. Live status detail: `docs/rubric_selfcheck.md`, `BUILD_LOG.md`.

- **Repo:** github.com/TejasviTyagi14/anki (branch `mockups-mcat-handwriting`),
  a public **AGPL-3.0-or-later** fork of Anki. Credit + third-party licenses:
  `README.md`, `THIRD_PARTY_NOTICES.md`.
- **Exam:** **MCAT** (472–528); primary output the **Chem/Phys sub-score 118–132**
  for organic-chemistry mechanisms (`README.md` → "Exam & scope").

## How to reproduce everything (make targets)
| Command | What it shows |
| --- | --- |
| `make test` | Rust engine tests (`cargo test -p anki --lib mechgrader`) + Python engine/scoring/AI/sync/crash tests |
| `make test-grader` | RDKit deterministic grader suite — **69 passed** |
| `make test-ios-ffi` | native-engine FFI over `rslib` (host build of the iOS crate) |
| `make eval` | held-out grading vs human labels; RDKit baseline **agreement 0.867**; AI row when a key is set (`.env`) |
| `make leakage` | held-out vs training near-dup scan — **CLEAN** (15 held-out / 13 train) |
| `make bench` | 50k-card dashboard benchmark — `topic_mastery` **p95 ≈ 38 ms** |
| `make scores` | the three scores with ranges + a give-up **abstention** |
| `make ios` | build + launch the iOS app (native `rslib` engine + editor) in the Simulator |
| `make sync-ios-verify` | **phone→desktop** card sync on the shared engine → **PASS** |
| `make grader` | serve the editor + RDKit grader at http://localhost:8000 |

## 1. Hand-in checklist (spec §12)
| Deliverable | Where | Status |
| --- | --- | --- |
| Public AGPL fork, credit to Anki | `LICENSE`, `README.md`, `THIRD_PARTY_NOTICES.md` | ✅ |
| Exam stated up front | `README.md` → "Exam & scope" | ✅ |
| Build instructions (both apps) | `README.md` → "Build & run — both apps" | ✅ |
| Architecture overview | `README.md` → "Architecture" | ✅ |
| Note on the Rust change | `docs/rust_change.md` | ✅ |
| List of files touched | `docs/touched_files.md` | ✅ |
| Demo video (3–5 min) | script + shot list: `docs/demo_script.md` | ▶ record from the script |
| Model descriptions (memory/perf/readiness + give-up) | `docs/model_memory.md`, `docs/model_performance.md`, `docs/model_readiness.md`, `docs/give_up_rule.md` | ✅ |
| Brainlift | `BRAINLIFT.md` | ✅ |

## 2. Grading rubric → proof (spec §11)
| Area (weight) | Proof / status |
| --- | --- |
| Rust change & fit (20%) | Real `MechgraderService` (`rslib/src/mechgrader/`): `topic_mastery` + engine RPC. `cargo test` (5 unit) + Python integration + undo-safety, all via `make test`; reachable through the real backend; runs **natively on iOS**. `docs/rust_change.md`, `docs/touched_files.md` |
| Score accuracy & honest uncertainty (20%) | Three scores (`mechgrader/scoring/`), each a **range**; readiness **abstains** below the give-up line (`make scores`). Calibration harness (Brier/log-loss/ECE) + paraphrase bridge built + tested. Real-student calibration honestly pending (`docs/model_*.md`, `docs/results.md`) |
| Study feature on learning science (15%) | Pre-registered 3-arm interleaving experiment (`mechgrader/experiment/`, `docs/study_feature.md`), fair (shows the null region). Simulation, labeled |
| AI checking & safety (15%) | `mechgrader/ai/` + `mechgrader/eval/`: env-only key + kill switch, prompt-injection posture, **citation-or-drop**, deterministic clamping; held-out eval vs a baseline with **pre-registered cutoffs**. Honest result: `gpt-4o-mini` did **not** beat the baseline on agreement (0.667 vs 0.867) and we report it (`docs/ai_eval.md`) |
| Re-runnable fair tests (12%) | Every `make` target above; `chem-grader/` tracked so a clean clone runs them; leakage caught+fixed a real bug |
| One engine + working sync (10%) | Same `rslib` on desktop (PyO3) + **iOS (native C-FFI)**; **phone→desktop sync** `make sync-ios-verify` → PASS; conflict CRDT (10 tests) (`ios/rust-ffi/`, `mechgrader/sync/`, `docs/mobile.md`) |
| Useful product & clean UX (8%) | Web editor (flashcard flow, click-to-draw, curved arrows, live RDKit grade), desktop `.dmg`, iOS app (native engine + editor + sync). `docs/reviewer_loop.md`, `docs/installer.md` |

## 3. Hard limits → standing (spec §11)
| Hard limit | Standing |
| --- | --- |
| No real Rust change → 50% | **Cleared** — real, tested, reachable, runs on the phone |
| No engine-sharing syncing phone → 70% | **Addressed** — native `rslib` on iOS + `make sync-ios-verify` PASS (Simulator + localhost; physical-device signing is the last-mile) |
| No re-runnable test setup → 60% | **Cleared** — `make` targets; `chem-grader/` committed |
| No held-out testing → 60% | **Cleared** — 15/13 split, leakage CLEAN, eval is held-out-only |
| Made-up/misleading readiness → auto-fail | **Avoided** — abstains; every number traces to an input; sims labeled |
| App not on a clean device → 50% | Desktop `.dmg` runs on a clean mac; iOS native app runs in the Simulator (physical device needs a dev cert) |
| Leaked test data → 0 | **Clean** (`make leakage`) after catching a real leak |
| AI claims with no source → AI 0 | **Avoided** — citation-or-drop enforced in code |

## 4. Concrete challenges (spec §7) → where
| # | Challenge | Where |
| --- | --- | --- |
| 7a | Rust change (+3 unit, +1 Python, undo, why-Rust, touched files) | `rslib/src/mechgrader/`, `docs/rust_change.md`, `docs/touched_files.md` |
| 7b | Sync test (offline both sides, conflict rule) | `mechgrader/sync/` (10 tests), `mechgrader/tools/sync_roundtrip.py`, `docs/sync_conflict_rule.md` |
| 7c | Coverage map (% covered, abstain below line) | `data/coverage/mcat_orgo_outline.json`, `mechgrader/scoring/` (`make scores`) |
| 7d | Paraphrase test (recall vs performance gap) | `mechgrader/paraphrase/`, `docs/model_performance.md` |
| 7e | Leakage check | `mechgrader/leakage/` (`make leakage` → CLEAN) |
| 7f | AI card check (gold set, 3 counts, cutoff) | `mechgrader/cardgen/`, `data/gold_qa/` |
| 7g | Crash + offline tests | `mechgrader/tests/test_crash_recovery.py` (zero corruption); AI-off path |
| 7h | One-command benchmark | `make bench` (p50/p95/worst) |

## 5. Deadlines (spec §6) → status
- **Wednesday (core, no AI):** Rust change + 3 unit + 1 Python test ✓; review loop ✓; memory model + give-up ✓; desktop installer ✓; phone runs the deck on the shared engine ✓.
- **Friday (AI + sync):** AI sourced + checked + baseline comparison ✓ (honest: cheap model didn't beat it); AI-off still scores ✓; phone↔desktop sync ✓ (`make sync-ios-verify`).
- **Sunday (prove + ship):** calibration/perf/readiness methods + ranges ✓; study feature 3-arm ✓; leakage/bench/crash ✓; desktop `.dmg` + iOS build ✓; honest reporting incl. what didn't work ✓.

## 6. Honest gaps (stated, not hidden)
- **Mobile** runs in the iOS **Simulator** against a **localhost** sync server on one
  machine (real Anki protocol) — a signed physical-device install + a two-physical-
  device sync are the last-mile. Android needs an SDK not present here.
- **AI vs baseline** verified only with `gpt-4o-mini` (didn't clear the bar); a
  frontier model is expected to — set a key in `.env` and re-run `make eval`.
- **Score calibration on real students** is out of reach in a week; the harnesses
  run and are tested on labeled simulations, which are labeled as such.
- Reviewer **GUI** wiring inside the Qt app is documented, not driven headlessly.

## 7. Repo map (key paths)
- `rslib/src/mechgrader/` — the Rust engine change. `proto/anki/mechgrader.proto`.
- `ios/rust-ffi/`, `ios/MechGrader/` — native engine FFI + the SwiftUI app.
- `web/mechgrader/` — the shared editor bundle (+ vendored RDKit-JS).
- `mechgrader/` — grading, scoring, AI, eval, sync, leakage, bench, calibration,
  experiment, paraphrase, tools.
- `chem-grader/` — RDKit deterministic grader (wrapped by `mechgrader/grading`).
- `data/` — coverage outline + held-out gold sets. `sources/registry.json`.
- `docs/` — this index, model pages, rust change, touched files, mobile, results,
  ai_eval, give_up_rule, demo_script, rubric_selfcheck, installer, robustness.
