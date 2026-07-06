# BRAINLIFT — MechGrader

> A Brainlift captures the point of view behind the build: what we believe, why,
> and the evidence. Everything here is grounded in what was actually built and is
> reproducible with a `make` target; nothing is aspirational.

## Owner
_(your name / handle)_ — repo: **github.com/TejasviTyagi14/anki** (branch
`mockups-mcat-handwriting`).

## Purpose
Build the **honest** version of an organic-chemistry *mechanism* study tool: a
student draws a full reaction mechanism (structures + curved electron-pushing
arrows) and gets a traceable, automatic grade, with **three separate scores**
(Memory, Performance, Readiness) on **one shared Rust engine** across desktop and
phone — and **re-runnable proof for every claim**.

## Scope & exam
**MCAT** (total 472–528). Primary output is the **Chem/Phys sub-score (118–132)**
for the organic-chemistry mechanism content that appears on Chem/Phys and
Bio/Biochem. It does not claim to cover the whole MCAT; Readiness is coverage-
weighted and **abstains below the give-up line**. (`README.md`,
`docs/model_readiness.md`, `docs/give_up_rule.md`.)

## The one belief that overrides everything
**A confident number with nothing behind it is worse than an honest "not enough
data yet."** Every displayed score traces to computed evidence; the app abstains
when data is thin; the AI won't speak without a citation; every claim is a
re-runnable command. Honesty over flattery — that is the whole product.

## Spiky POVs (contrarian bets this project makes)
1. **Abstention is a feature, not a bug.** Fabricated readiness is an automatic
   fail; `readiness()` returns *no number* below the give-up line and says exactly
   what's missing (`make scores` shows both a projection and an abstention).
2. **Mechanisms are structured data, not pixels.** Honest grading needs
   atom-mapped SMILES + arrows-as-tuples checked by RDKit (canonical SMILES /
   InChIKey / valence / substructure), not image "vibes."
3. **Recalling "SN1" ≠ drawing SN1 for a new substrate.** Memory and Performance
   are *different models* and must be measured separately — the paraphrase/bridge
   test exists to prove Performance isn't just a copy of Memory.
4. **One engine or it doesn't count.** The phone runs the *same* Rust `rslib`
   engine (iOS via a C-FFI over `rslib`; Android via `rsdroid`), not a JS/Swift
   reimplementation of the scheduler.
5. **AI is allowed only if it's sourced, checked, and beats a simpler baseline** —
   and if it doesn't, we say so. It didn't, with a cheap model, and we reported it.

## Evidence / sources
- **Chemistry ground truth:** six real texts registered in `sources/registry.json`
  (Clayden *Organic Chemistry* 2e, Wade 9e, Klein 4e, McMurry 9e, Carey 11e,
  Lehninger 8e). Every gold item and reference mechanism resolves to a named
  source; the AI grader must cite a rubric line + reference step or its judgment
  is dropped (`mechgrader/registry/`, `docs/ai_eval.md`).
- **Learning science (interleaving):** pre-registered hypothesis + primary metric
  in `docs/study_feature.md`; the three-arm experiment (`mechgrader/experiment/`)
  is a fair test that *could* fail (and shows the null region at low
  confusability).
- **Engine / shared-architecture facts:** `docs/rust_change.md`, `docs/mobile.md`,
  `BUILD_LOG.md`, and the native iOS engine banner ("MechGrader engine live on
  Anki 26.05").

## Categories (knowledge tree)
- Spaced repetition / FSRS memory model (Anki `rslib`).
- Cheminformatics grading (RDKit: canonical SMILES, InChIKey, SMARTS, Morgan).
- Score modeling & honest uncertainty (Wilson intervals; Brier/log-loss/ECE
  calibration; coverage-weighted readiness mapping; the give-up rule).
- Shared-engine architecture (one `rslib` → desktop PyO3, iOS C-FFI, Android JNI).
- AI safety (env-only keys, kill switch, prompt-injection posture, citation-or-drop,
  deterministic clamping, held-out eval vs a baseline with pre-registered cutoffs).

## What worked, and what honestly did not
- **Worked:** real Rust change (`topic_mastery`) tested + reachable; RDKit grader
  (69 tests); three scores with ranges + abstention; native iOS engine + a real
  phone→desktop sync round-trip; leakage-clean held-out eval; 50k-card benchmark;
  crash recovery with zero corruption; desktop `.dmg`.
- **Did not (reported honestly):** a cheap AI model (`gpt-4o-mini`) did **not**
  beat the RDKit baseline on pass/fail agreement (0.667 vs 0.867) — although its
  numeric scores correlated *better* (Pearson 0.824 vs 0.745). The eval harness
  reported this instead of rubber-stamping the AI. Real-student calibration of the
  readiness score is out of reach in a week; we say so rather than fake a number.

## Open questions / risks
- **Physical-device mobile:** the phone runs the native engine + syncs in the iOS
  Simulator against a localhost server; a signed physical-device install + a
  two-device sync are the remaining last-mile (`docs/mobile.md`).
- **AI efficacy:** a frontier model is expected to clear the pre-registered bar;
  only verified with `gpt-4o-mini` here.
- **Interleaving:** whether it helps for *this* content is an open, fair question;
  the harness is built to answer it on a real cohort.

## Insights log (dated)
- **2026-07-05** — A services-only protobuf file generates no Rust module (prost
  needs a message); a dedicated `MechgraderService` keeps the upstream Anki diff to
  **four one-line edits** (`docs/touched_files.md`).
- **2026-07-05** — Building `anki` as a standalone lib for iOS missed `tokio`'s
  `io-util`/`fs` (the whole-workspace build hides it via feature unification); the
  FFI crate requesting `tokio` `full` lets `rslib` cross-compile to the iOS
  simulator. The phone then runs the *real* engine RPC natively.
- **2026-07-05** — The first gold split **leaked** (same reactions in train +
  held-out); `make leakage` caught 36 near-duplicates. Re-splitting by reaction
  group (union-find) made it CLEAN — the honesty loop caught a real bug.
- **2026-07-05** — Better MAE/correlation but *worse* pass/fail agreement is the
  signature of a model whose threshold is miscalibrated around the pass line — so
  the AI "failing" the bar is an honest, informative result, not a broken grader.
