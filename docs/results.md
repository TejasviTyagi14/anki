# Results (Stage 3)

> **Status: IN PROGRESS.** Re-runnable evidence; real numbers, including what
> didn't work. Each result names the command that reproduces it.

## Results so far

### Leakage scan — CLEAN (`make leakage`)
Held-out 15 / training 13; no held-out reaction near-duplicates any training/
few-shot/calibration input; no id spans splits. Method: canonical SMILES +
InChIKey (exact) + Morgan Tanimoto ≥ 0.9 (fuzzy).

**What didn't work at first (honest):** the initial gold split was by
attempt-variant, so the same reference reactions appeared in both splits —
`make leakage` flagged 36 leaks. Fixed by re-splitting into whole near-duplicate
reaction groups (`mechgrader/tools/resplit_gold.py`); now clean. (6 unit tests:
`mechgrader/tests/test_leakage.py`.)

### AI-grader eval — baseline done, AI pending key (`make eval`)
RDKit-only baseline on the leakage-clean held-out (n=15, seed 0): agreement
**0.867**, wrong-grade **0.133**, Pearson **0.745**, Spearman **0.722**, MAE
**19.87**. Pre-registered cutoffs (agreement ≥ 0.85, wrong-grade ≤ 0.05, beat
baseline on 3 metrics) are fixed; the AI row is blank until `MECHGRADER_LLM_*` is
set (no fabricated numbers). See `docs/ai_eval.md`.

## Still planned
1. **Memory calibration** — reliability diagram + Brier/log loss on held-out
   reviews. (`make eval` memory path.)
2. **Performance accuracy** — accuracy on held-out exam-style mechanisms, with a
   range.
3. **Readiness mapping** — the stated method + a projected Chem/Phys range (or an
   explicit abstention per the give-up rule).
4. **Paraphrase test** — recall-vs-performance gap over 30 cards × 2 reworded
   reactions.
5. **Study-feature experiment** — three-build result at equal study time vs. the
   pre-registered metric (`docs/study_feature.md`); report the range and any null
   result.
6. **AI eval + baseline** — held-out accuracy, wrong-grade rate vs. pre-registered
   cutoff, and the AI-beats-RDKit-only table (`docs/ai_eval.md`).
7. **Leakage** — `make leakage` output showing the train/few-shot/calibration
   inputs are clean of held-out/gold near-duplicates.
8. **Benchmarks** — `make bench` p50/p95/worst-case on the 50k-card deck vs. the
   Section-10 targets (button < 50ms p95; next card < 100ms p95; dashboard first
   load < 1s p95; sync < 5s; cold start < 5s desktop / 4s phone).
9. **Reliability** — crash test (×20, both platforms, zero corruption) and
   offline test (AI off cleanly, both apps still score).
