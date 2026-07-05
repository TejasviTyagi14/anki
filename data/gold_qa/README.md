# data/gold_qa/ — gold Q&A for the card-generation check (7f)

**Status: seeded.** `gold_qa.json` holds **73** question/answer pairs with
**known-correct answers**, used to check AI-generated MechCards. The checker and
its pass/fail gate live in `mechgrader/cardgen/` and are unit-tested offline
(`mechgrader/tests/test_cardgen_check.py`).

Workflow (7f):

1. Generate cards from **one real source** (a chapter registered in
   `sources/registry.json`) via the env-gated seam
   `mechgrader/cardgen/generate.py`.
2. Run them through the checker (`mechgrader.cardgen.check.run_cardgen_check`)
   against this gold set.
3. It reports three counts — **correct+useful**, **wrong** (a wrong fact is worse
   than no card), **correct-but-bad-teaching** (vague/trivial/duplicate) — and a
   pass/fail against the **pre-registered** cutoff in
   `mechgrader/cardgen/PREREGISTERED.md`.
4. Every `wrong` and every `bad_teaching` card is **blocked**
   (`blocked_cards(report)`).

## Item format (`gold_qa.json`)

```jsonc
{
  "id": "qa-0001",
  "source_ref": "clayden-2ed#ch15.2",   // "<source_id>#<locator>"
  "question": "…",
  "answer": "…",                          // known-correct, short + checkable
  "acceptable_variants": ["…"],           // other correct phrasings
  "notes": "what makes a generated card 'useful' vs 'bad-teaching' here"
}
```

The top-level file is `{"schema_version", "description", "items": [...]}`; the
loader (`mechgrader.cardgen.check.load_gold_items`) also accepts a bare list.

## ⚠️ source_refs must be registered before real use

The `source_ref` values in `gold_qa.json` are **illustrative placeholders** that
name a textbook + chapter/section (e.g. `clayden-2ed#ch15.2`,
`lehninger-8ed#ch6.4`). They are **not yet entries in `sources/registry.json`**,
which currently ships only the deliberately non-resolvable `EXAMPLE-textbook`.

Before this gold set gates any real generated card:

1. **Register** each `source_id` in `sources/registry.json` (title, authors,
   edition, ISBN/DOI), and
2. **Verify** each locator against the physical source (the exact page/section
   that supports the answer).

This mirrors the guardrail enforced for MechCards in
`mechgrader/notetype/mechcard.py` (`resolve_source_ref` rejects unregistered and
placeholder sources): no card, reference mechanism, gold item, or AI judgment may
ship against an unresolvable `source_ref`.

## Honesty notes on the answers

`acceptable_variants` must stay reasonably complete: the checker is deterministic
and conservative, so an answer it cannot match to the gold answer or a variant is
counted as **wrong**. That costs *recall* (a good card may be blocked) but can
**never** let a wrong fact through. When you add items, keep answers short and
checkable, and do not put the answer verbatim into the question.
