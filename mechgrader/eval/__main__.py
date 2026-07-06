"""``python -m mechgrader.eval`` — the ``make eval`` entry point.

What it does, honestly:

* Loads and validates the held-out gold set in ``data/gold_mechanisms/``.
* Runs the **RDKit-only baseline** (``mechgrader.grading.deterministic``) when
  RDKit is importable; otherwise prints that it was skipped (no fake numbers).
* Runs the **AI rubric grader** only when ``MECHGRADER_LLM_PROVIDER`` and a real
  API key are set; otherwise prints exactly why it was skipped.
* When both ran, prints the baseline-vs-AI table and the PASS/FAIL against the
  **pre-registered** cutoffs (``PREREGISTERED.md``).

It never fabricates an AI number, and it always says which parts ran vs. were
skipped-for-missing-key / missing-RDKit.

Exit codes: 0 = something real was evaluated (and, if compared, cutoffs passed);
1 = comparison ran but failed the pre-registered cutoffs; 2 = nothing could be
evaluated (no gold, no RDKit, no AI).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from . import compare as compare_mod
from .ai_grader import AIGraderUnavailable, ai_grader_status, load_ai_grader
from .harness import load_gold_items, run_eval, split_counts, validate_gold_item


def _load_dotenv() -> Optional[str]:
    """Load a gitignored ``.env`` (repo root, else CWD) into the environment so
    the AI key can live in a file instead of being exported every shell.

    A variable already set in the real environment always wins (``setdefault``),
    and the key is never printed. Returns the path loaded, or None.
    """
    candidates = [Path(__file__).resolve().parents[2] / ".env", Path.cwd() / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        try:
            for raw in path.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                key, sep, val = line.partition("=")
                if sep and key.strip():
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
        except OSError:
            continue
        return str(path)
    return None


def _load_baseline():
    """Return the RDKit-only deterministic grader as a grader_fn, or None."""
    try:
        from mechgrader.grading.deterministic import grade_mechanism
    except Exception as exc:  # RDKit / chem-grader not installed here
        return None, str(exc)

    def baseline_fn(attempt, reference):
        return grade_mechanism(attempt, reference)

    return baseline_fn, None


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mechgrader.eval")
    parser.add_argument("--gold", default=None, help="gold file/dir (default: data/gold_mechanisms/)")
    parser.add_argument("--split", default="heldout", help="split to evaluate (default: heldout)")
    parser.add_argument("--seed", type=int, default=0, help="bootstrap seed (default: 0)")
    parser.add_argument("--json", action="store_true", help="also dump the raw metrics as JSON")
    args = parser.parse_args(argv)

    print("=" * 72)
    print("MechGrader eval — held-out grading vs. human labels")
    print("Cutoffs are PRE-REGISTERED (see mechgrader/eval/PREREGISTERED.md).")
    print("=" * 72)

    dotenv = _load_dotenv()
    if dotenv:
        print(f"[env]   loaded {dotenv} (shell-exported vars still win)")

    # --- gold set --------------------------------------------------------- #
    try:
        items = load_gold_items(args.gold)
    except FileNotFoundError as exc:
        print(f"[gold]  ERROR: {exc}")
        return 2
    problems: list[str] = []
    for it in items:
        problems.extend(validate_gold_item(it))
    counts = split_counts(items)
    print(f"[gold]  loaded {len(items)} items; splits = {counts}")
    if problems:
        print(f"[gold]  WARNING: {len(problems)} schema problem(s):")
        for p in problems[:20]:
            print(f"          - {p}")
    heldout = [it for it in items if it.get("split") == args.split]
    if not heldout:
        print(f"[gold]  ERROR: no items in split {args.split!r}; nothing to evaluate.")
        return 2

    # --- baseline (RDKit-only) ------------------------------------------- #
    baseline_fn, baseline_err = _load_baseline()
    baseline_metrics = None
    if baseline_fn is None:
        print(f"[base]  SKIPPED — RDKit deterministic grader unavailable: {baseline_err}")
        print("          (install RDKit in chem-grader/.venv to run the baseline)")
    else:
        print("[base]  running RDKit-only deterministic baseline...")
        baseline_metrics = run_eval(items, baseline_fn, seed=args.seed, split=args.split)
        print("[base]  done.")

    # --- AI rubric grader ------------------------------------------------- #
    ai_metrics = None
    status = ai_grader_status()
    if not status["available"]:
        print(f"[ai]    SKIPPED — {status['reason']}")
        print("          (no AI numbers are fabricated when the key is missing)")
    else:
        try:
            ai_fn, info = load_ai_grader()
            print(f"[ai]    running AI grader (provider={info['provider']}, model={info['model']}, "
                  f"deterministic_constraint={info['deterministic_constraint']})...")
            ai_metrics = run_eval(items, ai_fn, seed=args.seed, split=args.split)
            print("[ai]    done.")
        except AIGraderUnavailable as exc:
            print(f"[ai]    SKIPPED — {exc}")
        except Exception as exc:  # a configured call that failed at runtime
            print(f"[ai]    ERROR — AI grader failed at runtime: {exc}")

    # --- report ----------------------------------------------------------- #
    print("-" * 72)
    ran: dict = {}
    if baseline_metrics is not None:
        ran["baseline (RDKit-only)"] = baseline_metrics
    if ai_metrics is not None:
        ran["AI rubric"] = ai_metrics

    if not ran:
        print("Nothing was evaluated (no baseline, no AI). See the skip reasons above.")
        return 2

    print(compare_mod.format_table(ran))

    verdict = None
    if baseline_metrics is not None and ai_metrics is not None:
        verdict = compare_mod.evaluate_cutoffs(baseline_metrics, ai_metrics)
        print()
        print("Pre-registered cutoff check (fixed before results):")
        for c in verdict["checks"]:
            print(f"  [{'PASS' if c['passed'] else 'FAIL'}] {c['name']}: {c['detail']}")
        print()
        print(f"Overall AI-vs-baseline verdict: {verdict['verdict']}")
    else:
        print()
        print("No baseline-vs-AI comparison: need BOTH graders to have run.")
        if ai_metrics is None:
            print("  (AI was skipped; only the baseline ran — this is expected without a key.)")

    if args.json:
        print()
        print(json.dumps({"metrics": ran, "verdict": verdict}, indent=2, default=str))

    if verdict is not None:
        return 0 if verdict["passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
