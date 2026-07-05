"""``python -m mechgrader.bench`` — the ``make bench`` entry point.

Builds (and caches) a large collection with a realistic reaction-tagged subset,
then times the engine-side dashboard actions with p50 / p95 / worst-case (never a
single cherry-picked number), against the Section-10 speed budget.

    PYTHONPATH=out/pylib:. out/pyenv/bin/python -m mechgrader.bench [--cards 50000] [--tagged 3000] [--runs 30]
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from typing import Callable

import anki.collection

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from mechgrader.scoring import scores as scoring  # noqa: E402

# A spread of reaction types (matches data/coverage/mcat_orgo_outline.json ids).
REACTION_TYPES = [
    "SN1", "SN2", "E1", "E2", "EAS", "carbonyl_addition",
    "nucleophilic_acyl_substitution", "aldol", "oxidation", "reduction",
]
TAG_PREFIX = "mechgrader::reaction::"


def _pct(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return float("nan")
    idx = min(len(sorted_vals) - 1, int(q * (len(sorted_vals) - 1) + 0.5))
    return sorted_vals[idx]


def _time(fn: Callable[[], object], runs: int) -> dict:
    samples: list[float] = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000.0)  # ms
    samples.sort()
    return {
        "runs": runs,
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(_pct(samples, 0.95), 2),
        "worst_ms": round(samples[-1], 2),
        "mean_ms": round(statistics.fmean(samples), 2),
    }


def _build_collection(path: str, n_cards: int, n_tagged: int) -> float:
    """Generate the collection if missing. Returns generation seconds (0 if cached)."""
    if os.path.exists(path):
        return 0.0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    t0 = time.perf_counter()
    col = anki.collection.Collection(path)
    try:
        nt = col.models.by_name("Basic")
        did = col.decks.id("Bench")
        every = max(1, n_cards // max(1, n_tagged))
        tagged = 0
        for i in range(n_cards):
            note = col.new_note(nt)
            note["Front"] = f"card {i}"
            note["Back"] = "x"
            if i % every == 0 and tagged < n_tagged:
                rt = REACTION_TYPES[tagged % len(REACTION_TYPES)]
                note.tags = [f"{TAG_PREFIX}{rt}"]
                tagged += 1
            col.add_note(note, did)
        # Give the tagged cards a mechanism-pass count so the query parses
        # custom_data (mg_pass drives mastery). <=8-byte keys per Anki's limit.
        for cid in col.find_cards(f"tag:{TAG_PREFIX}*"):
            card = col.get_card(cid)
            card.custom_data = json.dumps({"mg_pass": 2, "mg_att": 3}, separators=(",", ":"))
            col.update_card(card)
    finally:
        col.close()
    return time.perf_counter() - t0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m mechgrader.bench")
    ap.add_argument("--cards", type=int, default=50000)
    ap.add_argument("--tagged", type=int, default=3000)
    ap.add_argument("--runs", type=int, default=30)
    ap.add_argument("--path", default=os.path.join(_REPO, "out", "mechgrader_bench",
                                                    "bench.anki2"))
    args = ap.parse_args(argv)

    print("=" * 72)
    print(f"MechGrader bench — {args.cards} cards ({args.tagged} reaction-tagged), "
          f"{args.runs} runs/action")
    print("=" * 72)

    gen_s = _build_collection(args.path, args.cards, args.tagged)
    print(f"collection: {args.path}")
    print(f"generation: {'cached' if gen_s == 0 else f'{gen_s:.1f}s'}")

    col = anki.collection.Collection(args.path)
    try:
        total = len(col.find_cards(""))
        tagged = len(col.find_cards(f"tag:{TAG_PREFIX}*"))
        print(f"cards: {total} total, {tagged} reaction-tagged\n")

        def topic_mastery():
            return list(col._backend.topic_mastery(
                search="", tag_prefix="", min_retrievability=0.0, min_pass_grades=0))

        topics = topic_mastery()

        # Scoring math on the query output (the dashboard's per-type performance).
        grades_by_type = {
            t.reaction_type: [80.0] * max(1, t.total_cards) for t in topics
        }

        def score_dashboard():
            return scoring.performance_by_type(grades_by_type)

        # "Dashboard first load" = the query + the scoring math together.
        def dashboard():
            ts = topic_mastery()
            g = {t.reaction_type: [80.0] * max(1, t.total_cards) for t in ts}
            return scoring.performance_by_type(g)

        results = {
            "topic_mastery (Rust query)": _time(topic_mastery, args.runs),
            "scoring math": _time(score_dashboard, args.runs),
            "dashboard (query + scoring)": _time(dashboard, args.runs),
        }
    finally:
        col.close()

    print(f"{'action':<32} {'p50':>8} {'p95':>8} {'worst':>8}  (ms)")
    print("-" * 62)
    for name, m in results.items():
        print(f"{name:<32} {m['p50_ms']:>8} {m['p95_ms']:>8} {m['worst_ms']:>8}")

    print("\nSection-10 targets (engine-side): dashboard first load p95 < 1000ms; "
          "refresh p95 < 500ms.")
    dash_p95 = results["dashboard (query + scoring)"]["p95_ms"]
    print(f"dashboard p95 = {dash_p95}ms -> "
          f"{'PASS' if dash_p95 < 1000 else 'OVER BUDGET'} vs 1000ms first-load target.")
    print("\nNote: button-press (<50ms), next-card (<100ms), and cold-start metrics "
          "require the running GUI app and are not measured here (headless).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
