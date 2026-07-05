# Model 3 — Readiness (required)

**Question it answers:** projected **MCAT Chem/Phys sub-score (118–132)** for the
orgo mechanism content, with a range and a "how sure" note.

## Method (stated, not hand-waved)
1. Compute **Performance** per reaction type (Model 2).
2. Weight each reaction type by its share of MCAT orgo emphasis
   (`data/coverage/mcat_orgo_outline.json` weights) **and** by coverage (types
   the deck doesn't cover contribute uncertainty, not points).
3. Map the coverage-weighted performance to the 118–132 band via a stated
   monotonic mapping, propagating uncertainty into a **range** (not a point).
4. **Respect the give-up rule** (`docs/give_up_rule.md`): below the line →
   abstain, don't project.
5. Full **472–528** projection only when coverage crosses the threshold across
   Chem/Phys + Bio/Biochem orgo content; always with a wide range + coverage
   caveat. Default: Chem/Phys only.

## Honesty (Section 9 — grade the steps of the bridge)
- Step 1 calibrated memory — required (Model 1).
- Step 2 predict held-out exam-style correctness — required (Model 2).
- Step 3 turn performance into a score **with a stated method + range** — required (this page).
- Step 4 validate against real students — **bonus; not available in a week.**
- We will explicitly say "we calibrated memory but do not yet have data to prove
  the projected score" where that is true — that scores higher than a polished
  number we can't back up.

## Coverage map (7c)
Every MCAT orgo reaction type is listed in `data/coverage/mcat_orgo_outline.json`
with a weight and a `covered` flag; the dashboard shows % covered and abstains
below the line. A big deck skipping a high-weight section must not show "ready."

## Status
Method fixed. The mapping + range implementation and validation land in Stage 3;
the projected number is gated by the give-up rule and shown with caveats.
