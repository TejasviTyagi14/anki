# Pre-registered passing cutoff for the card-generation check (7f)

**Status: PRE-REGISTERED. Fixed before any generation run.**
Changing these numbers requires a new dated entry below with a written reason —
they may **not** be tuned after seeing a batch's results (that would let a bad
batch redefine "passing").

This file is the human-readable source of truth; the same numbers are mirrored in
code as `mechgrader.cardgen.check.DEFAULT_PASS_CUTOFF` so a drift between prose and
code is a bug.

## The cutoff (v1, 2026-07-05)

A batch of generated cards **passes** (may ship) only when **all three** hold:

| Metric                          | Rule            | Rationale |
| ------------------------------- | --------------- | --------- |
| `correct_useful` fraction       | **>= 90%**      | Most cards must be both correct and worth studying. |
| `wrong` count                   | **== 0** (0 tolerated) | A wrong fact is worse than no card. A single wrong card fails the whole batch, regardless of how good the rest are. |
| `bad_teaching` fraction         | **<= 10%**      | Some correct-but-weak cards are acceptable, but they are still **blocked** individually. |

`correct_useful + wrong + bad_teaching == total`, so the three fractions sum to 1.

### What "pass" does and does not mean

* **Pass** means the *batch* cleared the bar. Every `wrong` and every
  `bad_teaching` card is still individually **blocked** (`blocked_cards(report)`);
  only `correct_useful` cards are eligible to ship.
* **Fail** means the batch is rejected. In particular, **one wrong card fails the
  batch even at 90% correct**, because `max_wrong == 0`.

### Honesty notes (why the counts are trustworthy)

* The checker is **deterministic** (no model in the loop) and **conservative**:
  an answer it cannot verify against the gold answer or an acceptable variant is
  counted as **wrong**, not quietly passed. Incompleteness in the gold set's
  `acceptable_variants` therefore costs *recall* (a good card may be blocked) and
  can **never** let a wrong fact through.
* A detected factual **contradiction** (e.g. Markovnikov vs anti-Markovnikov,
  ortho/para vs meta, inversion vs retention) forces `wrong` even when the card
  shares most of its wording with the gold answer.
* Duplicates are downgraded to `bad_teaching`, never silently dropped, so the
  denominator stays honest.

## Cutoff shape (for reference)

```json
{
  "min_correct_useful_frac": 0.90,
  "max_wrong": 0,
  "max_bad_teaching_frac": 0.10
}
```

## Change log

* **v1 — 2026-07-05** — Initial pre-registration. 90% / 0 / 10%.
