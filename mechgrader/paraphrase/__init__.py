"""Paraphrase / bridge test (rubric 7d): does the Performance model measure
something Memory doesn't?

For each of ~30 cards, author 2 exam-style reactions testing the same mechanism
class with a NEW substrate. Compare the student's *recall* on the card (memory)
with their *mechanism accuracy* on the reworded reactions (performance). If the
two are basically equal (and highly correlated), the performance model is just
copying memory and no bridge was built — report that honestly.

HONESTY: real recall-vs-performance data can't be gathered in a week, so the demo
here is a clearly-labeled SIMULATION (memorizing a fact transfers only partly to a
novel substrate). The `bridge_report` function is the real deliverable: feed it
real per-card recall + reworded-accuracy and it computes the gap the same way.

Pure stdlib.
"""

from __future__ import annotations

import math
import random
import statistics


def pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = statistics.fmean(xs), statistics.fmean(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return None  # undefined (no variance) — never faked as 0/1
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(sx * sy)


def bridge_report(items: list[dict]) -> dict:
    """items: [{card_id, recall in [0,1], reworded: [accuracy in [0,1], ...]}].

    Returns mean recall, mean reworded performance, the gap, their correlation,
    and a verdict on whether performance is a real bridge beyond memory.
    """
    recalls = [float(it["recall"]) for it in items]
    perfs = [statistics.fmean([float(x) for x in it["reworded"]]) for it in items]
    mean_recall = round(statistics.fmean(recalls), 4)
    mean_perf = round(statistics.fmean(perfs), 4)
    gap = round(mean_recall - mean_perf, 4)
    r = pearson(recalls, perfs)

    if abs(gap) < 0.05 and (r is None or r > 0.9):
        verdict = ("performance ~= memory: the performance model may just be copying "
                   "recall — bridge NOT demonstrated")
        bridge = False
    else:
        verdict = ("performance diverges from memory: the bridge measures something "
                   "recall does not")
        bridge = True
    return {
        "n_cards": len(items),
        "mean_recall": mean_recall,
        "mean_performance": mean_perf,
        "recall_minus_performance": gap,
        "recall_performance_pearson": None if r is None else round(r, 4),
        "bridge_demonstrated": bridge,
        "verdict": verdict,
        "note": "SIMULATION unless fed real per-card recall + reworded accuracy.",
    }


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def simulate(n: int = 30, seed: int = 0, transfer: float = 0.65) -> list[dict]:
    """Simulate a student who memorized card wording (high recall) but only
    partially transfers to novel substrates (lower, noisier performance)."""
    rng = random.Random(seed)
    items = []
    for i in range(n):
        recall = _clamp01(rng.gauss(0.85, 0.08))
        base = recall * transfer
        reworded = [round(_clamp01(base + rng.gauss(0.0, 0.12)), 3) for _ in range(2)]
        items.append({"card_id": f"card-{i:02d}", "recall": round(recall, 3), "reworded": reworded})
    return items
