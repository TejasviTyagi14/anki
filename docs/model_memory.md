# Model 1 — Memory (required, must be calibrated)

**Question it answers:** "What is P(recall) for *this card* right now?"

## Method
- Source: **Anki's FSRS retrievability** per card (already computed in `rslib`).
  MechGrader reads it; it does not reinvent it.
- Displayed as a **range**, never a bare number, with a "how sure" indicator and
  a calibration caveat until Stage 3 evidence exists.
- Kept strictly separate from Performance and Readiness (mixing the three is the
  easiest way to fail).

## Calibration plan (Stage 3 — required evidence)
- On **held-out reviews**, bin predicted P(recall) and compare to observed recall
  → **reliability diagram** + **Brier score** (and/or log loss).
- Claim to support: "when it says 80%, ~80% actually recall."
- Seeded, re-runnable; data + chart land in `docs/results.md`.

## Status
Wired to FSRS in Stage 1 (range display + give-up gating). Calibration evidence:
**pending Stage 3** — stated as such wherever shown.
