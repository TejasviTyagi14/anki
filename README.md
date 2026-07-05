# MechGrader

**MechGrader is a fork of [Anki](https://apps.ankiweb.net) that turns a
spaced-repetition deck into an honest organic-chemistry *mechanism* trainer.** A
student is shown a reaction prompt, draws the full mechanism (structures +
curved electron-pushing arrows), submits, and gets a traceable grade — with three
separate scores and re-runnable proof behind every number.

> Fork of Anki (© Ankitects Pty Ltd, AGPL-3.0-or-later). MechGrader stays
> **AGPL-3.0-or-later**. Mobile companion is an **AnkiDroid** fork (GPL-3.0-or-later).
> See `THIRD_PARTY_NOTICES.md`.

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
   (`rslib/src/mechgrader/`). Native on desktop and on Android (via `rsdroid`
   rebuilt on the same `rslib`), so the Rust change ships to both. (`docs/rust_change.md`)
2. **Mechanism editor + grading client** — one TypeScript web bundle
   (`web/mechgrader/`: Ketcher + RDKit-JS + curved-arrow overlay + submit/grade
   UI), embedded in the desktop webview and the Android WebView. Written once.
3. **Scoring math** — the three scores computed from primitives (FSRS state,
   per-type mechanism grades, coverage) by deterministic functions in the shared
   layer, so both apps compute identical numbers offline. Only the LLM rubric
   grade is online-dependent.

## Build & run
Everything is a `make` target (which wraps Anki's `just` recipes). See `make help`.

```bash
make build         # build the desktop app (Rust + Python + web)
make run-desktop   # build & launch the desktop app (needs a display)
make test          # MechGrader engine tests (Rust + Python rsbridge probe)
make stage0-proof  # re-run the Stage 0 engine-liveness proof
```

- **Toolchain / build notes** (incl. the sandbox `tsx` caveat and proto gotchas):
  `BUILD_LOG.md`.
- **Mobile** (AnkiDroid on the shared engine): `docs/mobile.md` — *not yet built
  in this environment (no Android SDK); procedure documented.*

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
