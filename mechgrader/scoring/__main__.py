"""Demo: the three scores (Memory / Performance / Readiness) with ranges, plus
the give-up rule abstaining — the video's "three scores" shot in one command.

Run:  make scores        (or:  python -m mechgrader.scoring)

Every number is computed by the real scoring functions from explicit inputs —
nothing is hardcoded. Memory is an FSRS P(recall) pass-through; Performance is the
observed k/n with a 95% Wilson interval; Readiness is the stated coverage-weighted
projection onto 118-132 (or an explicit abstention). See docs/model_*.md and
docs/give_up_rule.md.
"""

from __future__ import annotations

import json
import pathlib

from .scores import memory_score, performance_by_type, readiness

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTLINE = json.loads((ROOT / "data/coverage/mcat_orgo_outline.json").read_text())


def _seeded_grades(type_id: str, n: int, acc_pct: int) -> list[bool]:
    """Deterministic correct/incorrect list at ~acc_pct accuracy (no RNG state)."""
    h = sum(ord(c) for c in type_id) + 1
    out: list[bool] = []
    for i in range(n):
        h = (h * 1103515245 + 12345 + i * 2654435761) & 0x7FFFFFFF
        out.append((h % 100) < acc_pct)
    return out


def _show(label: str, d: dict) -> None:
    if d.get("abstained"):
        print(f"  {label:16s} ABSTAINED — {d['reasons'][0]}")
    else:
        pt, rng = d["point"], d["range"]
        print(f"  {label:16s} {pt:7.3f}  range [{rng['low']:.3f}, {rng['high']:.3f}]")
        if d.get("how_sure"):
            print(f"  {'':16s}   how sure: {d['how_sure']}")


def main() -> int:
    print("=" * 78)
    print("MechGrader — three scores (Memory / Performance / Readiness) + give-up rule")
    print("=" * 78)

    print("\n[1] MEMORY — P(recall) per card (FSRS pass-through, shown as a range):")
    _show("card w/ history", memory_score(0.82))
    _show("brand-new card", memory_score(None))

    print("\n[2] PERFORMANCE — P(correct mechanism | reaction type) = observed k/n:")
    perf_demo = performance_by_type(
        {
            "SN2": _seeded_grades("SN2", 12, 83),
            "E1": _seeded_grades("E1", 3, 66),
            "aldol": _seeded_grades("aldol", 2, 50),  # <3 attempts -> abstains
        }
    )
    for tid, d in perf_demo.items():
        _show(tid, d)

    types = [rt["id"] for rt in OUTLINE["reaction_types"]]
    high = [rt["id"] for rt in OUTLINE["reaction_types"] if rt["weight"] == "high"]
    chosen = high + [t for t in types if t not in high][:6]  # 14/20 types, all high
    grades = {t: _seeded_grades(t, 12, 68 + (i % 4) * 6) for i, t in enumerate(chosen)}
    perf = performance_by_type(grades)
    attempts = {t: len(g) for t, g in grades.items()}
    total = sum(attempts.values())
    print(
        f"\n[3] READINESS — projected Chem/Phys (118-132) from {total} attempts across "
        f"{len(chosen)}/{len(types)} types (all high-weight covered):"
    )
    r = readiness(perf, OUTLINE, {**attempts, "total_attempts": total})
    _show("Chem/Phys", r)
    if not r.get("abstained"):
        print(f"  {'':16s}   % exam covered: {r['pct_exam_covered']}%")

    print("\n[3b] READINESS — thin data → the give-up rule abstains (no number shown):")
    thin_perf = performance_by_type({"SN2": _seeded_grades("SN2", 4, 75)})
    thin = readiness(thin_perf, OUTLINE, {"SN2": 4, "total_attempts": 7})
    print(f"  {'Chem/Phys':16s} ABSTAINED (no point, no range). Why:")
    for reason in thin["reasons"][1:4]:
        print(f"  {'':16s}   - {reason}")

    print("\nEvery number traces to an explicit input; thin data abstains, never fabricates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
