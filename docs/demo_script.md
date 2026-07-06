# Demo video shot list (3–5 min)

Every required element mapped to an exact, working command/screen. Times are a
guide. Honest note: the one item not fully wired is a card synced *through the
phone UI* to desktop — see shot 3 for what is truthfully shown.

**Before recording:** `make grader` (serves the editor + RDKit grader at
http://localhost:8000) and `make ios` (builds + launches the native-engine app on
a booted iOS simulator).

---

### 1. Review session (~60s) — required
Open **http://localhost:8000**. Walk the flashcard loop:
- FRONT: the reaction prompt (e.g. "SN2: hydroxide + bromomethane…"). Press
  **Space** / click **Flip to start**.
- BACK: build structures (type SMILES or tap a quick-insert chip, or **✎ Draw**),
  push curved arrows (click a source atom/bond/lone-pair then a target), watch the
  **Assembled JSON** update live.
- Press **Enter** / **Submit** → the **RDKit deterministic grade** appears
  (pass/fail + score + reasons) and the **Reference** is revealed side-by-side.
- Click **Continue →** to the next card; show **Prev/Next** preserve each card's
  state. Mention the shortcuts (Space flip / Enter submit / ←→ prev-next).

### 2. The Rust change, in action (~45s) — required
- Run `make test` — point out `cargo test -p anki --lib mechgrader` (the engine
  unit tests) then `stage0_engine_probe.py` and `test_topic_mastery.py` calling the
  **`MechgraderService` RPC through the real backend** (rsbridge/PyO3).
- Cut to the **iOS Simulator**: the top banner reads **"MechGrader engine live on
  Anki 26.05 (&lt;hash&gt;)"** — the *same* Rust `mechgrader_engine_info` RPC running
  **natively on the phone** (via `ios/rust-ffi`). Same engine, two clients.

### 3. A card synced, phone ↔ desktop (~40s) — required (honest scope)
- Run `make sync-roundtrip`: it starts Anki's **own** self-hosted sync server, makes
  a card on collection **A**, uploads it, then a fresh collection **B** syncs down
  and the card appears — **`card_found=True → PASS`**. Server + both clients are the
  same forked engine (the desktop analogue of phone↔desktop sync).
- Show the iOS app (shot 2) running that same engine natively.
- **Say plainly:** the reproducible round-trip is engine-level (two collections via
  the real Anki sync protocol); wiring the iOS app's *sync button* to call
  `sync_collection` through the FFI is the remaining last-mile (`docs/mobile.md`).

### 4. The three scores, with ranges (~40s) — required
- Run `make scores`. Show:
  - **Memory** 0.820 range [0.770, 0.870] (FSRS pass-through) — and a brand-new card
    **abstaining**.
  - **Performance** per type (SN2 0.75 [0.47, 0.91] on 12 attempts; a type with <3
    attempts **abstains**).
  - **Readiness** projected **Chem/Phys ~128 [124, 131]**, % covered + "how sure",
    then a **thin-data case that abstains** (no number) with the give-up reasons.
- One line: every number traces to an explicit input; thin data abstains.

### 5. AI features + safety (~35s) — required
- Show `mechgrader/ai/` + `make test` running `test_ai_grader.py`: the AI grader is
  **citation-required** ("no citation, no credit"), **clamped** (can't beat the
  deterministic verdict), and has a **kill switch**.
- Run `make eval`: the **RDKit baseline** scores on held-out data; the **AI row
  abstains** because no key is set ("no AI numbers fabricated"). To show a live AI
  grade, set `MECHGRADER_LLM_PROVIDER`/`_API_KEY` (or a local `ollama` base URL) and
  re-run — see `docs/ai_eval.md`.

### 6. Test results (~40s) — required
Run and show the outputs:
- `make test` — Rust + Python engine/scoring/AI/sync/crash-recovery tests green.
- `make test-grader` — RDKit grader suite (**69 passed**).
- `make eval` — held-out baseline (agreement **0.867**, wrong-grade **0.133**).
- `make leakage` — **CLEAN** (held-out disjoint from training).
- `make bench` — 50k-card dashboard **p95 ≈ 38ms**.

---

### Coverage of the rubric's required shots
| Required in the video | Shot | Command |
| --- | --- | --- |
| A review session | 1 | `make grader` → localhost:8000 |
| Rust change in action | 2 | `make test`, `make ios` |
| Card synced phone→desktop | 3 | `make sync-roundtrip` (+ iOS app); last-mile noted |
| Three scores with ranges | 4 | `make scores` |
| AI features | 5 | `make test` (AI tests), `make eval` |
| Test results | 6 | `make test-grader`, `make eval`, `make leakage`, `make bench` |
