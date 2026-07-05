# BRAINLIFT — MechGrader

> A Brainlift captures the point of view behind the build: what we believe, why,
> and the evidence. Sections marked **[OPERATOR]** are course-specific (per
> Patrick's class outline) and should be completed by the human operator — they
> depend on your framing and are intentionally left for you rather than
> auto-filled.

## Purpose
Build the *honest* version of an orgo-mechanism study tool: a student draws a
full reaction mechanism and gets a traceable grade with three separate scores
(Memory, Performance, Readiness), on one shared engine across desktop and mobile,
with re-runnable proof for every claim.

## Owner
**[OPERATOR]** — your name / handle and role.

## Scope & exam
MCAT (472–528); primary output is the **Chem/Phys sub-score (118–132)** for orgo
mechanism content on Chem/Phys and Bio/Biochem. Coverage-gated; abstains below
the give-up line. (See `README.md`, `docs/give_up_rule.md`.)

## Spiky POVs (contrarian beliefs this project bets on)
1. **A confident score with nothing behind it is worse than an abstention.**
   Abstaining is a feature; fabricated readiness is an automatic fail.
2. **Mechanisms must be structured data, not pixels.** Grading honestly requires
   atom-mapped SMILES + arrows-as-tuples, checked by RDKit — not vibes on an
   image.
3. **Recalling "SN1" ≠ being able to draw SN1 for a novel substrate.** Memory and
   performance are different models and must be measured separately (the
   paraphrase bridge test proves you didn't just copy memory).
4. **One engine or it doesn't count.** The phone must run the same Rust engine
   (rsdroid → rslib), not a JS/Swift reimplementation of the scheduler.
5. **AI is only allowed if it's sourced, checked, and beats a simpler baseline.**

## Evidence / sources
- Learning science for interleaving: **[OPERATOR]** add the specific citations you
  want to stand behind (see `docs/study_feature.md` for the pre-registration).
- Chemistry ground truth: textbook chapters / DOIs registered in
  `sources/registry.json` (every card, reference mechanism, gold item, and AI
  judgment resolves to a named source).
- Engine/shared-architecture facts: `BUILD_LOG.md`, `docs/rust_change.md`,
  `docs/mobile.md`.

## Categories (knowledge tree)
- Spaced repetition / FSRS memory model.
- Cheminformatics grading (RDKit: canonical SMILES, InChIKey, SMARTS, Morgan).
- Score modeling & calibration (Brier/log loss; coverage; readiness mapping).
- Shared-engine architecture (Rust `rslib` ↔ desktop + rsdroid).
- AI safety (prompt-injection hardening; sourced + checked + baseline-beating).

## Open questions / risks
- Mobile toolchain not present in the current environment (top risk to the
  10% shared-engine+sync section) — plan in `docs/mobile.md`.
- Curved-arrow capture ergonomics (fallback: store arrows as tuples first, render
  second).
- Whether interleaving actually helps here (a fair test that could fail).

## Insights log
**[OPERATOR]** — running list of what you learned as you built (dated entries).
Seed entry: *2026-07-05 — a services-only protobuf file generates no Rust module
(prost needs a message); dedicated MechGrader service keeps upstream diffs to
three 1-line edits. See `BUILD_LOG.md`.*
