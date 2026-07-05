# Robustness — adversarial cases the graders will try

How each adversarial case is (or will be) handled. Items marked **planned** are
implemented in the stage noted; this page is finalized with evidence in Stage 3.

| # | Adversarial case | Handling | Stage |
| --- | --- | --- | --- |
| 1 | Memorizes card wording, fails reworded questions | Paraphrase bridge test (7d) surfaces the recall-vs-performance gap; Performance uses mechanism grades, not recall | 3 |
| 2 | Huge deck skipping a high-weight topic | Coverage map + give-up rule → **abstain**, never "ready" | 1 |
| 3 | Two cards stating opposite facts | Source registry + validator flags unresolved/contradictory sources; deterministic grader is answer-key-based | 2 |
| 4 | Source file with hidden text to trick card-gen | Inputs treated as **data**, RDKit-validated; instruction-like text stripped; LLM can't override deterministic verdicts | 2 |
| 5 | Taps "Good" without reading | Mechanism grade (performance) is separate from FSRS rating (memory); confidence pre-rating + timing flag low-effort | 1–2 |
| 6 | Topic with almost no history | Per-type give-up gate (≥3 attempts) → that type abstains | 1 |
| 7 | Accurate but too slow | Timing stored as a performance feature; explicit edge case in Model 2 | 1–2 |
| 8 | AI cards correct-but-useless | Card-gen three-count check + passing cutoff blocks them | 2 |
| 9 | Score jumps only because test items leaked | `make leakage` (canonical SMILES + InChIKey + Morgan near-dup) → leaked score zeroed | 3 |
| 10 | AI offline / rate-limited / broken JSON | Schema validation + retries + graceful fallback to deterministic grade; global kill switch | 2 |
| 11 | Same card on two devices offline, then sync | Conflict rule: logical/server timestamp last-write-wins + conflict log; attempts keyed by card+UUID so none are lost | 2 |
| 12 | Phone offline mid-sync or wrong clock | Logical timestamps (not device clock) → correct convergence | 2 |
| 13 | Crash mid-review | Clean recovery, zero corrupted collections (crash test ×20 both platforms) | 3 |
| 14 | Corrupt deck / 50k-card deck / broken images | Import validation; 50k bench; missing-media handled without crash | 3 |

## Status
Table fixed. Evidence (crash test, offline test, leakage run, paraphrase result)
is produced in Stage 3 and linked from `docs/results.md`.
