# Model 2 — Performance (required — the whole point of a mechanism grader)

**Question it answers:** "P(correct mechanism on a *new* reaction of type T)" —
from mechanism grades, not from recall.

## Method
- Inputs (distinct from memory): per-attempt **mechanism grades** (deterministic
  + AI rubric), reaction **difficulty**, **timing** (a student accurate but too
  slow is an explicit edge case), **hint usage** (a hinted-correct answer is
  weaker evidence), and **coverage**.
- Aggregated per reaction type; a type is only scored with ≥ 3 graded attempts
  (else it abstains — see `docs/give_up_rule.md`).
- "Mastered" (used by the Rust `TopicMastery` query): FSRS retrievability ≥ 0.90
  **and** ≥ N passing mechanism grades (N default 2).

## The bridge (paraphrase test, 7d — Stage 3, required)
Take 30 cards; for each, author 2 exam-style reactions testing the same mechanism
class with a **new substrate**. Compare the student's **recall on the card** vs.
**mechanism accuracy on the reworded reactions**. If the two numbers are ~equal,
the performance model is just copying memory and the bridge isn't built — report
the gap honestly. (Orgo is ideal: recalling "SN1" as a fact ≠ drawing SN1 for a
novel substrate.)

## Evidence (Stage 3 — required)
Accuracy on **held-out exam-style mechanisms**; report with a range.

## Status
Design fixed. Grades feed it in Stage 1–2; held-out accuracy + paraphrase gap:
**pending Stage 3.**
