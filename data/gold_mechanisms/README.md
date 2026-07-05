# data/gold_mechanisms/ — held-out graded mechanism attempts

**Status: empty until Stage 2** (`make gold` builds it).

Honest gold set for evaluating the grader(s). Since real longitudinal student
data can't be gathered in a week, each item is a **reference mechanism** plus
**deliberately-varied attempts** with a **human-assigned grade**:

- `correct`, `one-arrow-wrong`, `wrong-intermediate`, `wrong-product`,
  `valence-invalid`, `right-product-unbalanced`, `valid-alternative-route`, …

A fraction is **held out** and must never be used for LLM prompt/few-shot or
calibration fitting. `make leakage` (Stage 3) enforces this using canonical
SMILES + InChIKey + Morgan-fingerprint near-duplicate detection over mechanisms.

## Item format (planned JSON)
```jsonc
{
  "id": "gold-0001",
  "reaction_type": "SN1",
  "source_ref": "clayden-2ed#ch15.2",   // must resolve in sources/registry.json
  "reference": { /* structured mechanism: ordered steps, atom-mapped SMILES, arrows */ },
  "attempt":   { /* same schema */ },
  "human_grade": 0.0,                     // 0..100 or 0..1, human-assigned
  "human_labels": ["wrong-intermediate"],
  "split": "train | heldout"
}
```
