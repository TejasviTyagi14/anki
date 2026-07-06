# MechGrader

**MechGrader is a fork of [Anki](https://apps.ankiweb.net) that turns a
spaced-repetition deck into an honest organic-chemistry *mechanism* trainer.** A
student is shown a reaction prompt, draws the full mechanism (structures +
curved electron-pushing arrows), submits, and gets a traceable grade — with three
separate scores and re-runnable proof behind every number.

> Fork of Anki (© Ankitects Pty Ltd, AGPL-3.0-or-later). MechGrader stays
> **AGPL-3.0-or-later**. Mobile companion is an **AnkiDroid** fork (GPL-3.0-or-later).
> See `THIRD_PARTY_NOTICES.md`.

> **Grading this?** Start with **[`docs/SUBMISSION.md`](docs/SUBMISSION.md)** — a
> one-page index mapping every deliverable, rubric line, and hard limit to its
> proof and the command that reproduces it. The Brainlift is `BRAINLIFT.md`.

## Exam & scope (stated up front)
- **Exam:** MCAT (scored **472–528**); the Chem/Phys section is **118–132**.
- **MechGrader's scope:** the **organic-chemistry reaction/mechanism** content
  that appears on MCAT **Chem/Phys** and **Bio/Biochem**. It does **not** claim to
  cover the whole MCAT.
- **Primary output:** projected **Chem/Phys sub-score (118–132)**, with a range
  and a confidence. A full 472–528 projection is shown only when coverage crosses
  the give-up threshold, always with a wide range and a coverage caveat.

## Honesty caveats (the one rule that overrides everything)
We trust honest numbers over flattering ones. No displayed score is invented,
hardcoded, or rounded to look good — every score traces to computed evidence, and
the app **abstains** when data is insufficient (`docs/give_up_rule.md`). AI
grading is off until it is sourced, checked on held-out data, and beats a simpler
baseline. Current honest status (incl. what isn't done yet) lives in
`docs/rubric_selfcheck.md` and `BUILD_LOG.md`.

## The three scores (separate models)
- **Memory** — FSRS P(recall) per card, shown as a range; calibrated in Stage 3. (`docs/model_memory.md`)
- **Performance** — P(correct mechanism on a *new* reaction of type T), from mechanism grades, not recall. (`docs/model_performance.md`)
- **Readiness** — projected Chem/Phys sub-score, coverage- and give-up-gated. (`docs/model_readiness.md`)

## Architecture (one shared engine, not two apps)
1. **Rust engine** — Anki's `rslib` + MechGrader's `MechgraderService`
   (`rslib/src/mechgrader/`: `topic_mastery`, `mechgrader_engine_info`). The **same
   crate** runs on **desktop** (via `rsbridge`/PyO3), on **iOS** (via
   `ios/rust-ffi`, a C FFI cross-compiled to the iOS simulator — the app calls the
   real engine RPC natively), and on **Android** (via `rsdroid`/JNI, once the SDK
   is present). So the Rust change ships to every client.
   (`docs/rust_change.md`, `docs/mobile.md`)
2. **Mechanism editor + grading client** — one framework-free web bundle
   (`web/mechgrader/`: an SVG click-to-draw structure editor + curved electron-
   pushing arrow overlay + a flashcard review flow + submit/grade UI), embedded in
   the desktop webview and the phone `WebView`. Written once. (Ketcher and RDKit-JS
   are optional, documented seams — not required.)
3. **Deterministic grader** — RDKit (`chem-grader/` + `mechgrader/grading/`) checks
   canonical SMILES / InChIKey / valence / substructure; the editor's Submit calls
   it for a real grade, with an offline string fallback.
4. **Scoring math** — the three scores from primitives (FSRS state, per-type
   mechanism grades, coverage) by deterministic pure-stdlib functions
   (`mechgrader/scoring/`), so every client computes identical numbers offline.
   Only the optional LLM rubric grade (`mechgrader/ai/`) is online-dependent.
5. **Sync** — Anki's own sync (`make sync-roundtrip` proves an A→server→B
   round-trip on the shared engine); mechanism attempts merge via a CRDT
   (`mechgrader/sync/`). (`docs/sync_conflict_rule.md`)

## Build & run — both apps
Everything is a `make` target (wrapping Anki's `just` recipes). Run `make help`.

**Desktop** (macOS/Linux/Windows):
```bash
make build              # build the desktop app (Rust + Python + web)
make run-desktop        # build & launch the desktop app (needs a display)
./tools/build-installer # package the installer (.dmg/.exe) — docs/installer.md
make grader             # serve the editor + RDKit grader at http://localhost:8000
```

**Phone — iOS (runs the NATIVE shared engine in the Simulator):**
```bash
make ios                # build ios/rust-ffi (native rslib engine) + the Swift app,
                        # then link + install + launch on a booted iOS simulator
```
On launch the app shows **"MechGrader engine live on Anki <ver> (<hash>)"** from
the real Rust RPC running natively on the phone, above the shared editor. Requires
Xcode. Full detail + the physical-device last-mile: `docs/mobile.md`.

**Phone — Android (AnkiDroid on the shared engine):**
```bash
make build-mobile       # honest toolchain preflight + exact reproducible steps
```
Needs the Android SDK/NDK (absent in this environment). `docs/mobile.md`.

**Tests / evidence (all re-runnable):**
```bash
make test               # Rust engine tests + Python engine/scoring/AI/sync tests
make test-grader        # RDKit deterministic grader suite (69 tests)
make test-ios-ffi       # native-engine FFI over rslib (host build of the iOS crate)
make eval               # held-out grading vs labels (RDKit baseline; AI when keyed)
make leakage            # held-out vs training near-duplicate scan (must be CLEAN)
make bench              # 50k-card engine dashboard benchmark
make sync-roundtrip     # real A -> self-hosted server -> B sync round-trip
```

- **Build/toolchain notes** (proto gotchas, the tokio-feature fix for iOS):
  `BUILD_LOG.md`, `docs/mobile.md`.
- **List of files touched** (for a clean rebase onto upstream Anki):
  `docs/touched_files.md`.

## Docs & registries
`docs/rust_change.md`, `docs/touched_files.md`, `docs/mobile.md`,
`docs/give_up_rule.md`, `docs/model_memory.md`, `docs/model_performance.md`,
`docs/model_readiness.md`, `docs/study_feature.md`, `docs/ai_eval.md`,
`docs/sync_conflict_rule.md`, `docs/robustness.md`, `docs/results.md`,
`docs/demo_script.md`, `docs/rubric_selfcheck.md`; `BRAINLIFT.md`;
`sources/registry.json`; `data/coverage/mcat_orgo_outline.json`;
`data/gold_mechanisms/`, `data/gold_qa/`. Prototype grader: `chem-grader/`.

## License & attribution
AGPL-3.0-or-later (`LICENSE`). MechGrader credits **Anki** (Ankitects Pty Ltd)
and **AnkiDroid** (AnkiDroid Open Source Team). Third-party components (Ketcher —
Apache-2.0; RDKit — BSD-3-Clause) are attributed in `THIRD_PARTY_NOTICES.md`.

---

# Upstream: Anki

This repository is a fork of Anki; the upstream project's README follows.

[![Build Status](https://github.com/ankitects/anki/actions/workflows/ci.yml/badge.svg)](https://github.com/ankitects/anki/actions/workflows/ci.yml)
[![Documentation](https://img.shields.io/badge/docs-dev--docs.ankiweb.net-blue)](https://dev-docs.ankiweb.net)

This repo contains the source code for the computer version of
[Anki](https://apps.ankiweb.net).

## About

Anki is a spaced repetition program. Please see the [website](https://apps.ankiweb.net) to learn more.

## Getting Started

### Contributing

Want to contribute to Anki? Check out the [Contribution Guidelines](./docs/contributing.md).

For more information on building and developing, please see [Development](./docs/development.md).

#### Contributors

The following people have contributed to Anki: [CONTRIBUTORS](./CONTRIBUTORS)

### Anki Betas

If you'd like to try development builds of Anki but don't feel comfortable
building the code, please see [Anki betas](https://betas.ankiweb.net/).

## License

Anki's license: [LICENSE](./LICENSE)
