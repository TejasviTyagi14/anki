# Upstream files touched & future-merge difficulty

An honest accounting of what MechGrader changes in the upstream Anki tree, so a
future rebase onto upstream Anki is predictable. Design goal: **keep new code in
new files; touch upstream files with the smallest possible diffs.**

## Upstream Anki files edited (the ENTIRE core diff — all tiny + additive)
| File | Change | Merge risk |
| --- | --- | --- |
| `rslib/src/lib.rs` | `+ pub mod mechgrader;` (alphabetical) | **Very low** — one line in a sorted module list. |
| `rslib/proto/src/lib.rs` | `+ protobuf!(mechgrader, "mechgrader");` | **Very low** — one line in the proto module list. |
| `rslib/proto/python.rs` | `+ import anki.mechgrader_pb2` in the generated-header list | **Very low** — one line. |
| `Cargo.toml` (workspace) | `+ "ios/rust-ffi"` to `[workspace] members` | **Very low** — one line; adds a leaf member. |

That is the complete list of edits to files that exist in upstream Anki. Everything
else below is **new files/dirs** (no merge conflict risk). MechGrader deliberately
uses a *dedicated service in its own proto file* instead of adding RPCs to a core
service, so all engine logic stays in `rslib/src/mechgrader/` and off upstream's
hot paths. (`Cargo.lock` also updates, as expected.)

## New files & directories (additive — no merge risk)

### Rust engine change (the "real Rust change")
| Path | Purpose |
| --- | --- |
| `proto/anki/mechgrader.proto` | `MechgraderService` (+empty `BackendMechgraderService`): `MechgraderEngineInfo`, `TopicMastery` + messages. |
| `rslib/src/mechgrader/mod.rs` | `impl MechgraderService for Collection` + engine-info unit test. |
| `rslib/src/mechgrader/mastery.rs` | `topic_mastery` query (FSRS retrievability + reaction-type tags) + 5 unit tests. |

### Phone (shared engine on iOS) + FFI
| Path | Purpose |
| --- | --- |
| `ios/rust-ffi/` | C-FFI `staticlib` crate over the `anki` engine crate; `mechgrader_engine_info` (+ host unit test). Cross-compiles to `aarch64-apple-ios-sim`. |
| `ios/MechGrader/` | SwiftUI app: calls the native engine RPC + hosts the shared web editor in a `WKWebView`. |
| `ios/build_sim.sh` | Builds the Rust FFI + Swift app, links, installs/launches on booted simulators. |

### Web editor (shared client, written once)
| Path | Purpose |
| --- | --- |
| `web/mechgrader/` | Framework-free mechanism editor: `editor.js`, `mechanism.js`, `arrows.js`, `draw.js` (SVG click-to-draw), `chem.js`, `rdkit.js`, `index.html`, `app.css` (burnt-orange theme + flashcard flow). |

### Python: grading, scoring, AI, sync, evidence
| Path | Purpose |
| --- | --- |
| `mechgrader/grading/` | Deterministic RDKit grader adapter (+ tests). |
| `mechgrader/scoring/` | Memory / Performance / Readiness + give-up rule (pure stdlib, 11 tests). |
| `mechgrader/notetype/` | MechCard notetype registration (+ tests). |
| `mechgrader/reviewer/` | Review pipeline: submit → grade → `mg_pass` (+ test). |
| `mechgrader/ai/` | Provider-agnostic AI rubric grader (kill switch, citation-required, clamped; 11 tests). |
| `mechgrader/eval/` | Held-out eval harness + pre-registered cutoffs + baseline vs AI (7 tests). |
| `mechgrader/registry/`, `mechgrader/cardgen/` | Source validator; card-gen quality checker. |
| `mechgrader/sync/` | Attempt CRDT (logical-timestamp LWW, wrong-clock-safe; 10 tests). |
| `mechgrader/leakage/` | RDKit near-duplicate leakage scan (+ tests). |
| `mechgrader/bench/`, `mechgrader/calibration/`, `mechgrader/experiment/`, `mechgrader/paraphrase/` | Benchmarks; calibration (Brier/log-loss/ECE); study-feature experiment; paraphrase bridge. |
| `mechgrader/tools/` | `stage0_engine_probe.py`, `sync_roundtrip.py`, `resplit_gold.py`, `mobile_preflight.sh`. |
| `mechgrader/tests/` | Integration tests (`test_topic_mastery.py`, `test_crash_recovery.py`, …). |

### Data, prototype grader, docs, build
| Path | Purpose |
| --- | --- |
| `chem-grader/` | RDKit grader + FastAPI (`/mech/grade`, serves the editor at `/`); wrapped by `mechgrader/grading`. |
| `data/gold_mechanisms/`, `data/gold_qa/`, `data/coverage/` | Held-out gold sets (leakage-clean split) + MCAT orgo coverage outline. |
| `sources/registry.json` | Source registry (real texts) for AI citation validation. |
| `Makefile` | All build/test/eval/bench/leakage/ios/sync targets. |
| `README.md` (MechGrader header), `BUILD_LOG.md`, `THIRD_PARTY_NOTICES.md`, `BRAINLIFT.md`, `docs/*.md` (MechGrader docs) | Fork overview, build log, attributions, model/architecture/results docs. |

## Overall merge-difficulty assessment
**Trivial.** The upstream core diff is four one-line additive edits (a sorted
module list, a proto list, a generated-header import, and a workspace member).
Everything substantive is new files under `rslib/src/mechgrader/`, `ios/`,
`web/mechgrader/`, `mechgrader/`, `chem-grader/`, and `data/`. A rebase onto a
newer upstream Anki should apply cleanly. The one item that *would* raise risk —
a scheduler ordering hook for `points_at_stake` — was intentionally **not** taken;
`topic_mastery` needs no scheduler edits.
