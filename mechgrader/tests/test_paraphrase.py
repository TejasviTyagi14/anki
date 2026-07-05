#!/usr/bin/env python3
"""Stage 3: paraphrase/bridge test (7d) harness tests (pure stdlib).

Run:  PYTHONPATH=. python3 mechgrader/tests/test_paraphrase.py
"""

from __future__ import annotations

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from mechgrader.paraphrase import bridge_report, pearson, simulate


def test_equal_recall_and_performance_is_no_bridge():
    items = [{"card_id": f"c{i}", "recall": 0.9, "reworded": [0.9, 0.9]} for i in range(10)]
    r = bridge_report(items)
    assert r["recall_minus_performance"] == 0.0
    assert r["bridge_demonstrated"] is False  # performance == memory


def test_divergence_is_a_bridge():
    items = [{"card_id": f"c{i}", "recall": 0.9, "reworded": [0.5, 0.55]} for i in range(10)]
    r = bridge_report(items)
    assert r["recall_minus_performance"] > 0.3
    assert r["bridge_demonstrated"] is True


def test_pearson_known():
    assert abs(pearson([1, 2, 3], [1, 2, 3]) - 1.0) < 1e-9
    assert pearson([5, 5, 5], [1, 2, 3]) is None  # no variance -> undefined


def test_simulation_shows_recall_exceeds_performance():
    r = bridge_report(simulate(n=30, seed=0))
    assert r["n_cards"] == 30
    assert r["mean_recall"] > r["mean_performance"]  # memorization only partly transfers
    assert r["bridge_demonstrated"] is True


def test_deterministic():
    assert simulate(30, 0) == simulate(30, 0)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"\nOK: {len(tests)} paraphrase tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
