"""``python -m mechgrader.paraphrase`` — run the bridge test on a labeled
simulation and print the recall-vs-performance gap."""

from __future__ import annotations

from . import bridge_report, simulate


def main() -> int:
    print("=" * 72)
    print("MechGrader paraphrase / bridge test (7d) — recall vs mechanism accuracy")
    print("SIMULATION (memorizing a fact transfers only partly to a novel substrate).")
    print("=" * 72)
    items = simulate(n=30, seed=0)
    r = bridge_report(items)
    print(f"cards: {r['n_cards']} (x2 reworded reactions each)")
    print(f"mean recall (memory)         : {r['mean_recall']:.3f}")
    print(f"mean mechanism accuracy      : {r['mean_performance']:.3f}")
    print(f"recall - performance (gap)   : {r['recall_minus_performance']:+.3f}")
    print(f"recall/performance correlation: {r['recall_performance_pearson']}")
    print(f"\n{r['verdict']}")
    print("\nA gap near 0 with correlation ~1 would mean performance is just memory in")
    print("disguise; that would be reported as-is. Feed real data to bridge_report().")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
