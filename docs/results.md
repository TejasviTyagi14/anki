# Results (Stage 3)

> **Status: not started.** This page collects the re-runnable evidence produced
> in Stage 3. It will contain real numbers with ranges — including anything that
> didn't work — not polished claims. Each result names the command that
> reproduces it.

Planned contents:
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
