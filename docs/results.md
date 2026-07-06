# Results (Stage 3)

> **Status: IN PROGRESS.** Re-runnable evidence; real numbers, including what
> didn't work. Each result names the command that reproduces it.

## Results so far

### Leakage scan — CLEAN (`make leakage`)
Held-out 15 / training 13; no held-out reaction near-duplicates any training/
few-shot/calibration input; no id spans splits. Method: canonical SMILES +
InChIKey (exact) + Morgan Tanimoto ≥ 0.9 (fuzzy).

**What didn't work at first (honest):** the initial gold split was by
attempt-variant, so the same reference reactions appeared in both splits —
`make leakage` flagged 36 leaks. Fixed by re-splitting into whole near-duplicate
reaction groups (`mechgrader/tools/resplit_gold.py`); now clean. (6 unit tests:
`mechgrader/tests/test_leakage.py`.)

### AI-grader eval — baseline done, AI pending key (`make eval`)
RDKit-only baseline on the leakage-clean held-out (n=15, seed 0): agreement
**0.867**, wrong-grade **0.133**, Pearson **0.745**, Spearman **0.722**, MAE
**19.87**. Pre-registered cutoffs (agreement ≥ 0.85, wrong-grade ≤ 0.05, beat
baseline on 3 metrics) are fixed; the AI row is blank until `MECHGRADER_LLM_*` is
set (no fabricated numbers). See `docs/ai_eval.md`.

### Benchmarks — engine-side dashboard on 50k cards (`make bench`)
Collection: 50,000 cards, 3,000 reaction-tagged (generated in 9.3s, cached under
`out/mechgrader_bench/`). 30 runs/action, p50/p95/worst (ms):

| Action | p50 | p95 | worst |
| --- | --- | --- | --- |
| `topic_mastery` (Rust query) | 31.6 | 35.4 | 41.8 |
| scoring math | 0.39 | 0.49 | 0.60 |
| dashboard (query + scoring) | 32.1 | 38.0 | 105.8 |

Dashboard first-load **p95 = 38ms vs the 1000ms target → PASS** (~26× margin);
well under the 500ms refresh target too. This validates the design intent of
scoping `topic_mastery` by tag: it stays fast on a 50k-card collection because it
only visits the reaction-tagged subset via an indexed search.

**Honest scope:** these are the *engine-side* dashboard actions (the Rust query +
scoring math) measured headlessly. Button-press (<50ms), next-card (<100ms), and
cold-start (<5s) are GUI-app metrics that need the running desktop/phone app and
are **not** measured here — they require a display. Re-run: `make bench`.

### Memory calibration — machinery built + tested, real data pending (`python -m mechgrader.calibration`)
Reliability bins + Brier + log loss + ECE (`mechgrader/calibration/`, 6 tests). On
a clearly-labeled **simulation** the metric detects miscalibration:
well-calibrated ECE **0.016** vs overconfident ECE **0.148**. Honest per Section 9:
we can *compute* calibration and it works; real calibration needs real
longitudinal reviews (FSRS predicted vs actual recall from the revlog), which we
don't have — so no calibrated-memory *claim* is made yet.

### Ship — desktop BUILT; iOS runs the NATIVE shared engine
- **Desktop**: `out/installer/dist/anki-26.05-mac-apple.dmg` (215 MB, arm64) built
  via `./tools/build-installer`; the bundled `anki` wheel contains the
  `MechgraderService` engine change (verified). Adhoc-signed. See `docs/installer.md`.
- **iOS (native engine)** (`make ios`): `ios/rust-ffi/` cross-compiles the **same
  `anki`/`rslib` engine crate** to `aarch64-apple-ios-sim`; the SwiftUI app calls
  the real `mechgrader_engine_info` RPC natively and displays **"MechGrader engine
  live on Anki 26.05 (6acf80c0)"** in the iPhone/iPad Simulator, above the shared
  `web/mechgrader/` editor. Proves the phone runs the desktop's engine (not a
  reimplementation / not just a WebView). `cargo test -p mechgrader_ffi` green.
- **Android**: not buildable here — `make build-mobile` preflight shows 7/8
  prerequisites missing; exact reproducible steps provided. See `docs/mobile.md`.

### Working sync — phone → desktop on the shared engine
- **`make sync-roundtrip`**: collection **A** (1 note) → `full-upload`; fresh
  collection **B** → `full-download` → **1 note, card_found=True → PASS**.
- **`make sync-ios-verify`** (the iOS "Sync card → desktop" path): runs the
  *identical* native `mechgrader_ffi::sync_push` the Swift button calls, pushing a
  card to a self-hosted server; a desktop `Collection` then syncs it down →
  `[phone] pushed 1 card [full-upload]` → `[desktop] phone_card_found=True → PASS`.
- **Live**: `make sync-server` → tap the app button → `make sync-pull` prints
  `SN2 mechanism — synced from iPhone → PASS`.

Server + both clients are the same forked engine. Honest: one machine against a
localhost sync server (real Anki protocol), not two physical devices
(`docs/mobile.md`).

### Study-feature experiment — interleaving vs blocked vs plain (`python -m mechgrader.experiment`)
Fair three-arm SIMULATION (stated learner model; interleaving pays a switch cost
for cross-type discrimination, so it isn't rigged). Same learners (n=200), same
items, equal time, seed 0. Primary metric: novel mixed-type accuracy.

| arm | accuracy | 95% range |
| --- | --- | --- |
| interleaved | 0.873 | [0.741, 0.959] |
| blocked | 0.679 | [0.456, 0.873] |
| plain | 0.621 | [0.390, 0.840] |

interleaved − blocked = **+0.194** at orgo-like confusability (1.6). Confusability
sweep shows the fair crossover: at confusability 0 the delta is **−0.019**
(interleaving *hurts* — the switch cost with nothing to discriminate). 5 tests.
**Honest:** simulation, not real students; the harness runs on a real cohort by
swapping the simulated learner for logged data. A null/negative real result would
be reported as-is.

### Paraphrase / bridge test — recall vs performance (`python -m mechgrader.paraphrase`)
`bridge_report` compares per-card recall (memory) with reworded-reaction mechanism
accuracy (performance). SIMULATION (30 cards ×2 reworded): recall **0.844** vs
performance **0.536**, gap **+0.308**, r=0.54 → performance diverges from memory
(a real bridge, not memory in disguise). If they were equal & highly correlated it
would report "performance is just copying recall". 5 tests.

### Crash recovery — zero corrupted collections (`test_crash_recovery`)
Engine-level: (A) 20× unclean process exit right after a committed write →
integrity OK, all 20 notes survived; (B) hard SIGKILL mid write-loop (4,436 notes
in) → SQLite `pragma integrity_check` OK + Anki `fix_integrity` OK, no corruption.
(The GUI kill needs a display; the durability/no-corruption guarantee is the
collection's, tested here.)

### Offline / AI-off still scores
With no key or `MECHGRADER_AI_DISABLED` set, the AI grader returns
`ai_status="off"` and falls back to the deterministic grade (test_ai_grader), and
the scoring math is pure-stdlib (test_scoring) — so both apps still produce a
score offline.

### Source tracing — registry populated, gold resolves
`sources/registry.json` now holds 6 real texts (Clayden 2e, Wade 9e, Klein 4e,
McMurry 9e, Carey 11e, Lehninger 8e); every gold source_ref resolves (validated).

## Still planned
1. **Memory calibration** — reliability diagram + Brier/log loss on held-out
   reviews. (`make eval` memory path.)
2. **Performance accuracy** — accuracy on held-out exam-style mechanisms, with a
   range.
3. **Readiness mapping** — the stated method + a projected Chem/Phys range (or an
   explicit abstention per the give-up rule).
4. **Paraphrase test** — recall-vs-performance gap over 30 cards × 2 reworded
   reactions.
5. **Study-feature experiment** — three-build result at equal study time vs. the
   pre-registered metric (`docs/study_feature.md`); report the range and any null
   result.
6. **AI eval + baseline** — held-out accuracy, wrong-grade rate vs. pre-registered
   cutoff, and the AI-beats-RDKit-only table (`docs/ai_eval.md`).
7. **Leakage** — `make leakage` output showing the train/few-shot/calibration
   inputs are clean of held-out/gold near-duplicates.
8. **Benchmarks** — `make bench` p50/p95/worst-case on the 50k-card deck vs. the
   Section-10 targets (button < 50ms p95; next card < 100ms p95; dashboard first
   load < 1s p95; sync < 5s; cold start < 5s desktop / 4s phone).
9. **Reliability** — crash test (×20, both platforms, zero corruption) and
   offline test (AI off cleanly, both apps still score).
