#!/usr/bin/env python3
"""Re-split data/gold_mechanisms/gold.json so that no reference reaction (or a
near-duplicate) spans the train/held-out boundary — fixing the leakage that
`make leakage` detects when the set is split by attempt-variant.

Deterministic: items are grouped by near-duplicate reference (union-find), and
whole groups are assigned to held-out until ~40% of items are held-out, in a
fixed order. Only the ``split`` field changes.

Usage:
    PYTHONPATH=chem-grader/src:. chem-grader/.venv/bin/python \
        mechgrader/tools/resplit_gold.py [--apply] [--heldout-frac 0.4]
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from mechgrader.leakage.scan import mechanisms_near_dup

GOLD = os.path.join(_REPO, "data", "gold_mechanisms", "gold.json")


def _groups(items: list[dict]) -> list[list[int]]:
    n = len(items)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            dup, _ = mechanisms_near_dup(
                items[i].get("reference") or {}, items[j].get("reference") or {}
            )
            if dup:
                union(i, j)

    buckets: dict[int, list[int]] = {}
    for i in range(n):
        buckets.setdefault(find(i), []).append(i)
    # Deterministic order: by group size desc, then by smallest id.
    return sorted(buckets.values(), key=lambda g: (-len(g), min(str(items[k].get("id")) for k in g)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the new splits back")
    ap.add_argument("--heldout-frac", type=float, default=0.4)
    args = ap.parse_args(argv)

    items = json.load(open(GOLD))
    n = len(items)
    groups = _groups(items)
    print(f"{n} items -> {len(groups)} near-duplicate reaction groups:")
    for g in groups:
        rts = sorted({str(items[k].get("reaction_type")) for k in g})
        print(f"  group(size {len(g)}) types={rts}: {[items[k].get('id') for k in g]}")

    # Assign whole groups to held-out until ~heldout_frac of items are held-out.
    heldout_ids: set[int] = set()
    for g in groups:
        if len(heldout_ids) / n < args.heldout_frac and len(g) < n:
            heldout_ids.update(g)
    assignment = {"heldout": [], "train": []}
    for i, it in enumerate(items):
        split = "heldout" if i in heldout_ids else "train"
        assignment[split].append(it.get("id"))

    print(f"\nnew split: heldout={len(assignment['heldout'])} train={len(assignment['train'])}")
    if not args.apply:
        print("(dry run — pass --apply to write)")
        return 0

    for i, it in enumerate(items):
        it["split"] = "heldout" if i in heldout_ids else "train"
    with open(GOLD, "w") as fh:
        json.dump(items, fh, indent=2)
        fh.write("\n")
    print(f"wrote {GOLD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
