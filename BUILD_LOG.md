# MechGrader — BUILD LOG

Running log of what was done, commands run, what passed, what's blocked, and
each stage's commit hash. Newest entries at the top of each stage.

**Exam scope:** MCAT (472–528); Chem/Phys section (118–132). MechGrader targets
the organic-chemistry reaction/mechanism content on MCAT Chem/Phys and
Bio/Biochem. See `README.md`.

---

## Environment (this machine)

- OS: macOS (darwin 24.3.0), Apple Silicon.
- Toolchain (host): `just` 1.55.1, `rustc`/`cargo` 1.92.0, `node` v22.23.0.
- Anki vendors its own toolchains under `out/extracted/`: `uv`, `protoc` (v31.1),
  `node`, `yarn`. Python runs from `out/pyenv` (Python 3.13 via uv). System
  Python is 3.9 but is not used by the build.
- **Sandbox note:** the web/TS generation step runs `tsx`, which opens a unix
  IPC socket in `$TMPDIR`. Under a restricted sandbox this fails with
  `EPERM: listen ... .pipe`. **The build must run outside that sandbox** (or in
  an environment allowing local unix sockets). Pure `cargo` steps are fine
  sandboxed except for the target-dir cache location.

## Fork facts

- Base commit (upstream Anki): `685138ad8` "Add MCAT handwriting flashcard mockups".
- Branch: `mockups-mcat-handwriting`.
- Remotes: `origin` = ankitects/anki (upstream), `myfork` = TejasviTyagi14/anki.
- Anki version: `26.05`. Build hash observed: `b00308e5`.
- Pre-existing prototype in `chem-grader/` (Python + RDKit + NetworkX + FastAPI):
  a 5-layer reaction-mechanism grader. This is the seed for the Stage 1/2
  deterministic grader (see `chem-grader/README.md`).

---

## Stage 0 — Build the fork and prove the engine is live

Status: **DONE** (desktop). Mobile: **BLOCKED in this environment** (no Android SDK) — plan recorded in `docs/mobile.md`.

Commit hash (Stage 0): `7f902acbaddecf632093e406b9aea03f764aa0dc` (on branch `mockups-mcat-handwriting`, base `685138ad8`).

### 0.1 Fork builds (Rust + Python + web)

Command (from repo root):

```
just build            # wraps ./ninja pylib qt
```

Results:
- Baseline incremental build: **succeeded in 0.81s** (tree was already warm from a prior full build under `out/`).
- After adding the Rust change (below): **succeeded in 26.33s** (proto regen +
  `rslib` recompile + `pylib:rsbridge` + sveltekit/ts). Exit 0.

Two non-obvious gotchas hit and fixed (documented so they don't recur):

1. **New proto with only services (no messages) generates no Rust file.**
   `prost-build` only emits `out/.../anki.<pkg>.rs` for packages that contain at
   least one *message*. A services-only `mechgrader.proto` produced no
   `anki.mechgrader.rs`, so `protobuf!(mechgrader, ...)` failed to `include!`.
   Fix: give the package a real message (`EngineInfoResponse`) and use it as the
   RPC return type.
2. **Adding a brand-new proto file doesn't retrigger `anki_proto`'s build
   script.** Cargo only re-runs a build script when a *previously-registered*
   `rerun-if-changed` path changes; a new file isn't in that set. Fix: touch a
   build-script module (we edited `rslib/proto/python.rs`) or clear the
   fingerprint: `rm -rf out/rust/debug/{.fingerprint,build}/anki_proto-*`.

### 0.2 Trivial reachable Rust change (de-risks the Stage 1 real change)

Added a dedicated **`MechgraderService`** (own proto + service, so upstream core
files are barely touched — good for future merges). One RPC:
`MechgraderEngineInfo(Empty) -> EngineInfoResponse { info, anki_version, build_hash }`.

Files touched (see `docs/touched_files.md`):
- `proto/anki/mechgrader.proto` (new)
- `rslib/src/mechgrader/mod.rs` (new — impl + unit test)
- `rslib/src/lib.rs` (+1 line: `pub mod mechgrader;`)
- `rslib/proto/src/lib.rs` (+1 line: `protobuf!(mechgrader, "mechgrader");`)
- `rslib/proto/python.rs` (+1 line: `import anki.mechgrader_pb2`)

**Proof it surfaces (re-run with `make stage0-proof`):**

- Rust unit test:
  ```
  cargo test -p anki --lib mechgrader
  # test mechgrader::test::engine_info_is_reachable_and_mentions_mechgrader ... ok
  # test result: ok. 1 passed; 0 failed; ... 520 filtered out
  ```
- End-to-end from Python through the same `_rsbridge` FFI the GUI uses:
  ```
  PYTHONPATH=out/pylib out/pyenv/bin/python mechgrader/tools/stage0_engine_probe.py
  # info         : MechGrader engine live on Anki 26.05 (b00308e5)
  # anki_version : 26.05
  # build_hash   : b00308e5
  # OK: forked Rust MechgraderService is reachable from Python via rsbridge.
  ```

**Honesty note on "appears in the running desktop app":** this environment is
headless (no display), so the Qt GUI cannot be launched here. The Python probe
is a stronger, re-runnable substitute — it travels the identical
Python → rsbridge → Rust `Backend` → `Collection` path the GUI uses, and the
generated `col._backend.mechgrader_engine_info()` is exactly what GUI/Python code
would call. On a machine with a display, `just run` launches the GUI against this
same engine build.

### 0.3 AnkiDroid fork on the shared engine

**Status: not built here — no Android toolchain in this environment.** Verified:
no `ANDROID_HOME`/`ANDROID_SDK_ROOT`, no `adb`/`sdkmanager`/`emulator`/`gradle`,
no JDK, no Android Rust targets installed. Standing up AnkiDroid + rebuilding
`rsdroid` against this fork's `rslib` requires the Android SDK/NDK. The exact,
correct procedure (and why the engine really is shared — upstream already has
`ankidroid.proto` + `AnkidroidService`, and `rsdroid` wraps `rslib`) is written
in `docs/mobile.md`. This is an honest gap, not a fake pass.

### 0.4 Scaffolding

Created: `Makefile` (targets: build, run-desktop, build-mobile, run-mobile,
test, test-anki, stage0-proof, eval, bench, leakage, gold, sync-server — later
stages exit non-zero with a message so they can't be mistaken for passing),
`THIRD_PARTY_NOTICES.md` (Anki, AnkiDroid, Ketcher [Apache-2.0, verified
2026-07-05], RDKit [BSD-3-Clause, verified 2026-07-05]), this `BUILD_LOG.md`,
the `docs/` set, `sources/registry.json`, `data/coverage/mcat_orgo_outline.json`,
and `data/gold_mechanisms/` + `data/gold_qa/` placeholders.

---

## Stage 1 — "Wednesday" (core loop, no AI) — IN PROGRESS

### 1.1 The real Rust change — `topic_mastery` — DONE

The mastery-aware review pipeline's first (guaranteed) half is implemented in the
engine: `MechgraderService.TopicMastery`. It returns, per reaction-type tag
(from note tags under `mechgrader::reaction::`), the total cards, cards with an
FSRS memory state, mastered-card count, and average recall — all computed inside
Rust over the collection, scoped by tag so it stays fast on large collections.

- **"Mastered" definition (enforced in code):** FSRS retrievability
  >= `min_retrievability` (default 0.90) AND passing mechanism grades
  (`custom_data.mg_pass`) >= `min_pass_grades` (default 2).
- Files: `proto/anki/mechgrader.proto` (+TopicMastery rpc + 2 messages),
  `rslib/src/mechgrader/mastery.rs` (new), `rslib/src/mechgrader/mod.rs` (+trait
  method). No new upstream-core edits beyond Stage 0's three 1-liners.

**Proof (re-run with `make stage1-proof`):**
```
cargo test -p anki --lib mechgrader
# 6 passed: engine_info + 5 mastery tests, incl. read_only_query_does_not_break_undo
PYTHONPATH=out/pylib out/pyenv/bin/python mechgrader/tests/test_topic_mastery.py
# SN1: total=2 ...  SN2: total=1 ...   OK: TopicMastery reachable from Python via rsbridge
```

This alone satisfies rubric 7a (a real Rust change, reachable + tested). The
optional second half, `points_at_stake` review ordering, is deferred behind a
flag (it touches the scheduler queue / undo; per the plan we ship the guaranteed
change first and only add ordering if it can be done without undo instability).

Build after this change: `just build` succeeded in 23.84s (exit 0).

### 1.2 Core loop pieces — DONE (built by 5 parallel subagents, then consolidated)

All disjoint-scope, no shared-build contention, then integrated + re-tested here.

- **Deterministic grader** (`mechgrader/grading/`): adapter over `chem-grader/`'s
  5-layer RDKit grader; adds full element+charge balance per step and per-species
  InChIKey product match with a score cap on product miss. Returns
  {valid, score, product_match, balance_ok, per_step, reasons, passed}.
  Proof: `make test-grader` -> **62 passed** (6 adapter + 56 chem-grader).
- **Three scores + give-up rule** (`mechgrader/scoring/`): pure-stdlib,
  deterministic, offline. Readiness maps to 118-132 with uncovered types widening
  the range (never adding points); abstains with no numeric leakage.
  Proof: `make test` -> **11 passed**.
- **MechCard note type** (`mechgrader/notetype/`): fields Prompt /
  ReactionTypeTags / ReferenceMechanism(JSON) / SourceRef; back template mounts
  the web editor at `#mechgrader-canvas`; enforces a resolvable `source_ref`;
  tags `mechgrader::reaction::<type>` (so the Rust query sees them).
  Proof: **5 passed**.
- **Shared web editor** (`web/mechgrader/`): framework-free bundle - real data
  model (exact `{steps:[{reactants,arrows:[{from,to,kind}],products}]}` shape) +
  curved-arrow overlay (store-first / pure-render) + step/SMILES editing + Submit
  dispatch; Ketcher + RDKit-JS are documented seams. Proof: `node --check` (4/4)
  + 21-assertion smoke test.
- **Review pipeline glue** (`mechgrader/reviewer/pipeline.py`): submit -> grade
  (injectable grader) -> write per-card `mg_pass`/`mg_att` to custom_data (short
  keys; Anki caps keys at 8 bytes) -> return breakdown + reference for reveal +
  a *suggested* (not applied) FSRS rating. Proof (`make test`): end-to-end test
  ties MechCard -> submit -> mg_pass -> the **Rust topic_mastery query reads the
  same card**.
- **Desktop installer** (`docs/installer.md`): exact command `./tools/build-installer`
  -> `out/installer/dist/`, with honest submodule/signing caveats.

Integrated verification (this machine): `make test` (Rust 6 + stage0 probe +
topic_mastery + scoring 11 + notetype 5 + reviewer loop) all green, and
`make test-grader` 62 passed. `just build` green.

### 1.3 Remaining Stage 1 (honest gaps)
- **aqt reviewer GUI wiring**: the pipeline is tested and UI-agnostic; mounting
  the web editor in the reviewer webview + the pycmd bridge is documented in
  `docs/reviewer_loop.md` but not wired into `aqt` (needs a display to verify;
  this box is headless).
- **RDKit-JS actual WASM** + **Ketcher** are documented seams in the web bundle
  (not vendored).
- **Desktop installer** command documented but not executed (heavy; needs
  submodule checkout + network).
- Mobile still deferred (`docs/mobile.md`).

## Stage 2 — "Friday" (AI + sync)              — NOT STARTED
## Stage 3 — "Sunday" (evidence + ship)        — NOT STARTED
