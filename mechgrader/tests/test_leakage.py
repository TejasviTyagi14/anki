#!/usr/bin/env python3
"""Stage 3: leakage / near-duplicate detector tests (RDKit; run in chem-grader/.venv).

Run:
    PYTHONPATH=chem-grader/src:. chem-grader/.venv/bin/python -m pytest mechgrader/tests/test_leakage.py -q
"""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from mechgrader.leakage.scan import mechanisms_near_dup, scan_gold

SN1 = {"steps": [{"reactants": ["CC(C)(C)Br", "O"], "arrows": [], "products": ["CC(C)(C)O"]}]}
SN1_MAPPED = {
    "steps": [
        {
            "reactants": ["[CH3:1][C:2]([CH3:3])([CH3:4])[Br:5]", "[OH2:6]"],
            "arrows": [],
            "products": ["[CH3:1][C:2]([CH3:3])([CH3:4])[OH:6]"],
        }
    ]
}
SN2 = {"steps": [{"reactants": ["CCBr", "[OH-]"], "arrows": [], "products": ["CCO"]}]}


def test_identical_mechanisms_are_near_dup():
    dup, _ = mechanisms_near_dup(SN1, SN1)
    assert dup


def test_distinct_reactions_are_not_near_dup():
    dup, _ = mechanisms_near_dup(SN1, SN2)
    assert not dup


def test_atom_map_is_ignored():
    dup, _ = mechanisms_near_dup(SN1, SN1_MAPPED)
    assert dup, "atom-mapping must not defeat near-dup detection"


def test_scan_gold_clean():
    gold = [
        {"id": "t1", "split": "train", "reference": SN1},
        {"id": "h1", "split": "heldout", "reference": SN2},
    ]
    assert scan_gold(gold)["ok"]


def test_scan_gold_detects_leak():
    gold = [
        {"id": "t1", "split": "train", "reference": SN1},
        {"id": "h1", "split": "heldout", "reference": SN1},  # same reaction leaked in
    ]
    r = scan_gold(gold)
    assert not r["ok"]
    assert r["leaks"] and r["leaks"][0]["heldout_id"] == "h1"


def test_scan_gold_flags_duplicate_id_across_splits():
    gold = [
        {"id": "x", "split": "train", "reference": SN1},
        {"id": "x", "split": "heldout", "reference": SN2},
    ]
    r = scan_gold(gold)
    assert "x" in r["duplicate_ids"] and not r["ok"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\nOK: {len(tests)} leakage tests passed.")
