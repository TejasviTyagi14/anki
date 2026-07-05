# data/gold_qa/ — gold Q&A for the card-generation check (7f)

**Status: empty until Stage 2** (`make gold` builds it).

50 question/answer pairs with **known-correct answers**, used to check
AI-generated cards. Workflow (Stage 2):

1. Generate 50 cards from **one real source** (a textbook chapter registered in
   `sources/registry.json`).
2. Run them through a checker against this gold set.
3. Report three counts: **correct+useful**, **wrong** (a wrong fact is worse than
   no card), **correct-but-bad-teaching** (vague/trivial/duplicate).
4. Pre-set a passing cutoff; **block any card that fails it.**

## Item format (planned JSON)
```jsonc
{
  "id": "qa-0001",
  "source_ref": "clayden-2ed#ch15",     // must resolve in sources/registry.json
  "question": "…",
  "answer": "…",                          // known-correct
  "acceptable_variants": ["…"],
  "notes": "what makes a generated card 'useful' vs 'bad-teaching' here"
}
```
