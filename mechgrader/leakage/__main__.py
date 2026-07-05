"""``python -m mechgrader.leakage`` — the ``make leakage`` entry point.

Scans the gold set: no held-out reaction may near-duplicate any training /
few-shot / calibration input, and no id may span splits. Exit 0 = clean, 1 =
leakage found (which would zero the affected score), 2 = could not load gold.
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from mechgrader.eval.harness import load_gold_items

from .scan import DEFAULT_TANIMOTO, scan_gold


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mechgrader.leakage")
    parser.add_argument("--gold", default=None, help="gold file/dir (default: data/gold_mechanisms/)")
    parser.add_argument("--tanimoto", type=float, default=DEFAULT_TANIMOTO)
    args = parser.parse_args(argv)

    print("=" * 72)
    print("MechGrader leakage scan — held-out vs training/few-shot/calibration")
    print("Method: canonical SMILES + InChIKey (exact) + Morgan Tanimoto (fuzzy)")
    print("=" * 72)

    try:
        items = load_gold_items(args.gold)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        return 2

    report = scan_gold(items, tanimoto=args.tanimoto)
    print(f"held-out items : {report['n_heldout']}")
    print(f"training items : {report['n_train']}")
    print(f"tanimoto thresh: {report['tanimoto']}")

    if report["duplicate_ids"]:
        print(f"\nDUPLICATE IDS ACROSS SPLITS ({len(report['duplicate_ids'])}):")
        for i in report["duplicate_ids"]:
            print(f"  - {i}")

    if report["leaks"]:
        print(f"\nLEAKS FOUND ({len(report['leaks'])}):")
        for lk in report["leaks"]:
            print(f"  - held-out {lk['heldout_id']} ~ training {lk['training_id']}: {lk['reason']}")
        print("\nRESULT: LEAKAGE DETECTED — the affected held-out score is invalid.")
        return 1

    print("\nRESULT: CLEAN — no held-out reaction appears in the training inputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
