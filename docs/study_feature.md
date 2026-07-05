# Study-feature experiment — pre-registration

Pre-registered **before** running the experiment (Stage 3). Writing the
hypothesis and primary metric ahead of time is the point: a fair test that
*could* fail.

## Feature
**Interleaving of mechanistically-related reaction types** — mixing confusable
categories (e.g. SN1/SN2/E1/E2) within a session, instead of blocked practice
(one type at a time). Interleaving is well supported in the learning-science
literature for improving *discrimination* between confusable categories, which is
exactly the orgo failure mode (recognizing which mechanism a novel substrate
calls for). This ties directly to the `points_at_stake` Rust ordering.

## Pre-registered hypothesis (one sentence)
> Interleaving mechanistically-related reaction types will raise accuracy on
> **novel mixed-type mechanism questions** at equal study time, versus blocked
> practice; **failure = no improvement or a decrease.**

## Primary metric (named ahead of time)
Accuracy on a held-out set of **novel mixed-type mechanism questions** (new
substrates, mixed reaction types), graded by the deterministic grader, measured
at **equal total study time** across arms.

Secondary (reported, not decisive): per-type discrimination error (choosing the
wrong mechanism class), time-to-correct.

## Design — three builds, same learners, same questions, same time budget
1. **Full app, interleaving ON.**
2. **Full app, interleaving OFF (blocked)** — the ablation.
3. **Plain, unmodified Anki** — the baseline.

## Reporting rules
- Report a **range** (not a point estimate) and report **null results honestly**.
  "Interleaving made no difference here" is a real, publishable-for-this-project
  result. "Our app feels better" is not.
- Seed everything; record cohort assignment, item lists, and time budgets so
  `make` can reproduce.

## Status
Pre-registered. Experiment runs in Stage 3; results go in `docs/results.md`.
