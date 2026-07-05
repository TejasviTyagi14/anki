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

## Pre-registered cutoffs (fixed before any held-out AI number is looked at)
Locked in `mechgrader/eval/PREREGISTERED.md` and `mechgrader/eval/compare.py`
(`PREREGISTERED`). The AI grader passes only if **all** hold on the held-out split:
- Held-out **agreement with human grade** ≥ **0.85**.
- **Wrong-grade rate** (confidently wrong) ≤ **0.05**.
- **Beats the RDKit-only baseline** on **agreement**, **partial-credit
  correlation (Pearson)**, **and wrong-grade rate** (all three).

Pass line = 70/100; "clearly correct" = 90/100. Held-out split only; the harness
has no code path that fits/tunes on held-out (`mechgrader/eval/harness.py`).

## Baseline comparison (`make eval`, held-out n=15, leakage-clean)
Real numbers from the RDKit-only baseline on the held-out gold set (seed 0),
**after the held-out set was re-split to be leakage-clean** (see below / `make
leakage`). The AI row is **honestly blank until `MECHGRADER_LLM_*` is provided** —
no AI number is fabricated; `make eval` prints exactly why AI was skipped.

| Grader | n | Agreement (acc.) | Wrong-grade rate | Pearson | Spearman | MAE |
| --- | --- | --- | --- | --- | --- | --- |
| RDKit-only (baseline) | 15 | 0.867 | 0.133 | 0.745 | 0.722 | 19.87 |
| AI rubric (constrained) | — | pending key | pending key | pending key | pending key | pending key |

The baseline's 0.867 agreement and 0.133 wrong-grade rate straddle the AI's
pre-registered bar (0.85 / 0.05) — i.e. the baseline is exactly the simpler
method the AI must clear **and** beat. Re-run: `make eval` (needs `chem-grader/.venv`).

**Leakage note (honesty loop in action):** the first held-out split shared
reference reactions with the training split (it was split by attempt-variant, not
by reaction). `make leakage` caught it; the gold set was re-split so whole
near-duplicate reaction groups stay on one side (`mechgrader/tools/resplit_gold.py`),
and `make leakage` is now **CLEAN**. The tert-butyl SN1 and E1 items correctly
group together (mechanistically related — same substrate/carbocation), so they
never straddle the split.

**Status:** harness + gold set + metrics + baseline **implemented, tested, and run**
(7 harness tests via `make test`; baseline via `make eval`). AI grading numbers
land when a key is supplied.

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
