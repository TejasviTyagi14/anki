# The give-up rule (abstention)

**Abstaining is a feature, not a bug.** A "not enough data" message scores higher
than a fabricated number. This rule is enforced *in code* (Stage 1) — the app
renders no score below the line and states why.

## The rule (v1 — adjust only with a recorded reason)

A **Readiness** score (projected Chem/Phys sub-score, 118–132) is shown **only
when all** of the following hold:

1. **Volume:** ≥ **150** graded mechanism attempts total.
2. **Breadth:** attempts span ≥ **60%** of the MCAT orgo reaction-type outline
   (see `data/coverage/mcat_orgo_outline.json`).
3. **Depth on high-weight types:** ≥ **3** graded attempts in **each**
   `high`-weight reaction type.

If any condition fails, Readiness renders as
**"insufficient data — abstaining"** with the specific unmet condition(s) and
what is still needed (e.g. "need 42 more attempts; SN2 and EAS below 3 attempts").

### Per-model gates
- **Memory (FSRS P(recall)):** shown as a *range* as soon as a card has review
  history; no volume gate (it is a per-card property), but always with a
  calibration caveat until Stage 3 calibration evidence exists.
- **Performance (P(correct mechanism | type T)):** shown per reaction type only
  when that type has ≥ **3** graded attempts; otherwise that type abstains.
- **Readiness:** the full rule above.
- **Full 472–528 projection:** shown **only** when coverage also crosses the
  give-up threshold across MCAT Chem/Phys *and* Bio/Biochem orgo content, and
  **always** with a wide range and an explicit coverage caveat. Default: show
  Chem/Phys only.

## What every shown score must carry
Point estimate · likely range · % of exam covered · a "how sure" indicator ·
last-updated time · the main reasons · and a pointer to this rule.

## Where enforced (Stage 1)
- Scoring layer computes `coverage`, `attempts`, per-type depth from the shared
  primitives and returns an explicit `abstained: true/false` + `reasons[]`.
- The dashboard renders the abstention state; there is no code path that invents
  a number when `abstained` is true.
- A test asserts that below-threshold inputs produce `abstained: true` and that
  no numeric score is rendered.
