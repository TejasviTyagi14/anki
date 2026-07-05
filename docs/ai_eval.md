# AI grader evaluation (Stage 2) — plan & pre-registered cutoffs

The AI rubric grader (`mechgrader/ai/grader_llm.py`) assigns partial credit on
mechanism quality **on top of and constrained by** the deterministic RDKit
checks. No AI output ships without: (a) a resolvable `source_ref`, (b) held-out
eval against a **pre-registered** cutoff, (c) a side-by-side win over a simpler
baseline.

## Held-out gold set
Since honest longitudinal student data can't be gathered in a week, we build an
**honest gold set**: reference mechanisms + deliberately-varied attempts
(correct, one-arrow-wrong, wrong-intermediate, wrong-product, valence-invalid, …)
each with a **human-assigned grade**. A fraction is **held out** and never used
for prompt/few-shot/calibration fitting (enforced by `make leakage`).
Lives in `data/gold_mechanisms/`.

## Pre-registered cutoffs (fill BEFORE looking at held-out results)
> Record exact numbers here and commit them **before** running `make eval`.
- Minimum held-out **agreement with human grade**: `TBD` (e.g. ≥ 0.85).
- Maximum **wrong-grade rate** (confidently wrong): `TBD` (e.g. ≤ 5%).
- Must **beat the baseline** (RDKit-only: final-product match / fingerprint
  threshold) on: higher accuracy **and** better partial-credit correlation
  **and** lower wrong-grade rate.

## Baseline comparison (required table — Stage 2)
| Grader | Accuracy vs human | Partial-credit corr. | Wrong-grade rate |
| --- | --- | --- | --- |
| RDKit-only (baseline) | TBD | TBD | TBD |
| AI rubric (constrained) | TBD | TBD | TBD |

## Prompt-injection hardening (required)
- The LLM receives the **RDKit-validated structured mechanism as data**, never
  raw text that could carry instructions. Validate with RDKit before any LLM
  call; strip/ignore instruction-like content in inputs; the LLM **cannot
  override deterministic verdicts** (a wrong final product can't be graded
  "correct").
- Output is structured JSON: per-criterion scores, overall grade, and
  `source_refs` into the reference-mechanism step(s) + rubric line(s). No
  citation → judgment rejected. Schema-validate; retry on broken JSON; fall back
  to deterministic grade on failure.

## Card-gen check (7f — if we generate cards)
Build 50 gold Q&A (`data/gold_qa/`); generate 50 cards from one real source
(a textbook chapter); run a checker; report three counts: correct+useful, wrong
(worse than no card), correct-but-bad-teaching. Pre-set a passing cutoff; block
any card that fails it.

## AI-off path
Confirm the app still grades and still scores with AI disabled (falls back to the
deterministic grader). Global kill switch + test.

## Status
Design + pre-registration structure fixed. Numbers and tables produced in Stage 2
by `make eval`.
