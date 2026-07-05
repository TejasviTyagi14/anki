"""``python -m mechgrader.experiment`` — run the three-arm study-feature test and
print the pre-registered result + a confusability sweep. SIMULATION (stated
model); honest about what it is and isn't."""

from __future__ import annotations

from . import confusability_sweep, run_experiment


def main() -> int:
    print("=" * 74)
    print("MechGrader study-feature experiment — interleaving vs blocked vs plain")
    print("SIMULATION with a stated learner model (mechgrader/experiment/study_feature.py).")
    print("Not a claim about real students; the harness is ready for a real cohort.")
    print("=" * 74)

    r = run_experiment(seed=0)
    print(f"\nPre-registered primary metric: {r['primary_metric']}")
    print(f"Same learners (n={r['params']['n_learners']}), same items, "
          f"equal time (trials={r['params']['trials']}), confusability={r['params']['confusability']}\n")
    print(f"{'arm':<14}{'accuracy':>10}{'95% range':>22}")
    print("-" * 46)
    for arm in ("interleaved", "blocked", "plain"):
        a = r["arms"][arm]
        print(f"{arm:<14}{a['mean']:>10.3f}   [{a['range']['low']:.3f}, {a['range']['high']:.3f}]")
    print(f"\ninterleaved - blocked = {r['interleaved_minus_blocked']:+.3f}  ->  {r['verdict']}")

    print("\nConfusability sweep (fair test — shows where interleaving does NOT help):")
    print(f"{'confusability':>14}{'interleaved':>13}{'blocked':>10}{'delta':>9}")
    for row in confusability_sweep(seed=0):
        print(f"{row['confusability']:>14.1f}{row['interleaved']:>13.3f}"
              f"{row['blocked']:>10.3f}{row['delta']:>+9.3f}")
    print("\nReading: at confusability 0 interleaving's switch cost makes it <= blocked;")
    print("as confusable families get harder to tell apart, discrimination training wins.")
    print("A null or negative result here would be reported as-is — that's the point.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
