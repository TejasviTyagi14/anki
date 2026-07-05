# data/gold_mechanisms/ — held-out graded mechanism attempts

**Status: populated (Stage 2).** The gold set lives in
[`gold.json`](./gold.json) and is consumed by the evaluation harness in
`mechgrader/eval/` (`python -m mechgrader.eval`).

Honest gold set for evaluating the grader(s). Real longitudinal student data
can't be gathered in a week, so each item is a **reference mechanism** plus a
**deliberately-varied attempt** with a **human-assigned grade**.

> **These grades are AUTHOR REFERENCE LABELS, not real student data.** They were
> assigned by the author against the fixed rubric below. They are a stand-in for
> a real graded-student corpus and should be replaced/augmented with real,
> consented student attempts before any grading claim is published.

## Contents / counts

- `gold.json` — a JSON **array of 28 items**.
- Split: **16 `train`**, **12 `heldout`**.
- Reaction families: SN1, SN2, E1, E2, EAS, carbonyl (nucleophilic addition).
- Every variant appears in the held-out split; both splits are non-empty.

The **held-out** split must never be used for LLM prompt/few-shot content or for
calibration/threshold fitting. Only the `train` split may inform grader/prompt
design. `make leakage` (Stage 3) will additionally enforce this with canonical
SMILES + InChIKey + Morgan-fingerprint near-duplicate detection.

## Variants + the grading rubric

Each attempt carries one variant label; its human grade must fall inside the
band for that label (enforced by `mechgrader/eval/harness.py::validate_gold_item`,
so an inflated or mislabeled grade is caught):

| Variant label (`human_labels`) | Grade band | Meaning |
| --- | --- | --- |
| `correct` | 95–100 | Correct final product; every step mass/charge balanced; valid structures; correct curved arrows. |
| `valid-alternative-route` | 90–99 | Correct final product via a legitimate alternative mechanism (e.g. different valid base/proton source or step grouping). |
| `one-arrow-wrong` | 70–85 | Correct product and intermediates; exactly one incorrect curved (electron-pushing) arrow. |
| `right-product-unbalanced` | 45–65 | Correct final product drawn, but at least one step fails to conserve atoms/charge (a species is dropped). |
| `wrong-intermediate` | 30–50 | A chemically incorrect intermediate (e.g. the wrong carbocation / a non-contributing resonance form). |
| `wrong-product` | 10–25 | The final product is the wrong molecule. |
| `valence-invalid` | 0–10 | Contains a structure with an impossible valence (not a real molecule). |

**Pass line:** a grade `>= 70` is a *pass* (equal to the deterministic grader's
`PASS_THRESHOLD`). **Clearly correct:** `>= 90` (failing such an attempt is a
confidently-wrong grade). See `mechgrader/eval/PREREGISTERED.md`.

## Item format (JSON)

```jsonc
{
  "id": "gold-0001",
  "reaction_type": "SN2",
  "source_ref": "clayden-2e#ch15.1",   // must resolve in sources/registry.json before shipping
  "label_source": "author-reference",   // NOT real student data
  "human_grade": 100,                    // 0..100 (0..1 also accepted), human-assigned
  "human_labels": ["correct"],
  "split": "train",                      // "train" | "heldout"
  "grade_rationale": "…",                // one-line justification for the grade
  "reference": { "steps": [ /* … */ ] }, // structured mechanism (see below)
  "attempt":   { "steps": [ /* … */ ] }  // same schema
}
```

### Mechanism shape (matches the grader + web editor exactly)

```jsonc
{ "steps": [
  { "reactants": ["<atom-mapped SMILES>", "…"],
    "arrows":    [ { "from": "lp:3", "to": "atom:1", "kind": "curved" } ],
    "products":  ["<atom-mapped SMILES>", "…"] }
] }
```

Arrow endpoints use the web editor's convention — `atom:i`, `bond:i-j`, `lp:i`
(0-based positional index into the step's reactant bundle). Arrows are
**advisory** in the deterministic (RDKit-only) baseline, which is precisely why
`one-arrow-wrong` items are a place the AI rubric grader should be able to beat
the baseline.

## `source_ref` registration (required before shipping)

`source_ref` values point at real organic-chemistry textbooks
(`clayden-2e`, `wade-9e`, `mcmurry-9e`, `klein-4e`) and are formatted
`"<source_id>#<locator>"` so they *would* resolve. **They are not yet registered
in `sources/registry.json`** (which currently holds only the `EXAMPLE-textbook`
placeholder). Per that registry's own contract, each `source_id` used here must
be added — with a real title/edition/ISBN and the exact chapter/section verified
— before any card, mechanism, or AI judgment built on this gold set is shipped.
The eval harness validates the *format* of `source_ref`; it does not fabricate a
registry entry.
