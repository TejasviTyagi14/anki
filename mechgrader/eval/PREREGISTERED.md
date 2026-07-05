# Pre-registered evaluation cutoffs (MechGrader AI grader, Stage 2)

**These cutoffs are pre-registered. They are written down here BEFORE any
held-out result is looked at, and they are not to be changed in response to
results.** If a cutoff ever has to move, that is a new decision with its own
recorded reason and date — not a quiet edit to make a failing grader pass.

The machine-readable copy of these numbers lives in
`mechgrader/eval/compare.py` (`PREREGISTERED`); this file is the human record and
the two must agree.

## Why pre-register

The entire reason this harness exists is to stop "the AI grader looks good"
from becoming true by moving the goalposts. Fixing the bar in advance means the
held-out numbers can only confirm or deny a claim we already committed to — they
cannot be used to reverse-engineer a flattering threshold.

## The gold set and split

- Reference mechanisms + deliberately-varied attempts, each with an **author
  reference grade** (a human grade assigned by the author against the rubric in
  `data/gold_mechanisms/README.md`). These are **author reference labels, not
  real student data.**
- Metrics are computed on the **held-out** split only. The train split may be
  used to design/tune graders and prompts; the held-out split may **never** be.

## Definitions (as implemented in `mechgrader/eval/harness.py`)

- **Pass cutoff:** a grade (human or grader) is a *pass* iff `score >= 70`
  (equal to the deterministic grader's `PASS_THRESHOLD`).
- **Clearly correct:** a human grade `>= 90`.
- **Agreement (accuracy):** fraction of held-out items where the grader's
  pass/fail verdict equals the human's.
- **Wrong-grade rate (confidently wrong):** fraction of held-out items where the
  grader said **pass** but the human failed it, **or** the grader said **fail**
  but the human marked it clearly correct (`>= 90`).
- **Partial-credit correlation:** Pearson (primary) and Spearman correlation
  between the grader's 0–100 score and the human grade. Reported as `n/a` when a
  series has no variance (an undefined correlation is never reported as a number).

## Pre-registered cutoffs

The **AI rubric grader**, on the held-out split, must satisfy **all** of:

1. **Absolute agreement** with the human grade **≥ 0.85**.
2. **Absolute wrong-grade rate ≤ 0.05.**
3. **Beats the RDKit-only baseline on agreement** (strictly higher).
4. **Beats the RDKit-only baseline on partial-credit correlation** (strictly
   higher Pearson; both must be defined).
5. **Beats the RDKit-only baseline on wrong-grade rate** (strictly lower).

The verdict is **PASS** only if checks 1–5 all pass; otherwise **FAIL**. This is
exactly what `compare.evaluate_cutoffs` computes, and what `python -m
mechgrader.eval` prints.

## Baseline

The baseline is the **RDKit-only deterministic grader**
(`mechgrader.grading.deterministic.grade_mechanism`): final-product identity by
InChIKey + per-step mass/charge balance + chem-grader's layered structural score.
It does not read the rubric and only weakly considers arrows, so it is the
"simpler thing" the AI must beat to justify its cost and risk.

## Honesty guards baked into code

- No AI number is produced unless `MECHGRADER_LLM_PROVIDER` **and** the
  provider's API key are set (`mechgrader/eval/ai_grader.py`). There is no mock
  branch that could emit a fabricated AI metric.
- The AI cannot override a deterministic **wrong-final-product** or **invalid
  structure** verdict: such attempts are force-failed and score-capped.
- Every wrong grade in the report is listed with its item id, so the wrong-grade
  rate is auditable, not just asserted.
