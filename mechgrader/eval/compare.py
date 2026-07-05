"""Baseline-vs-AI comparison against **pre-registered** cutoffs.

The cutoffs below are pre-registered in ``mechgrader/eval/PREREGISTERED.md`` and
must be treated as fixed *before* any held-out number is looked at. This module
never changes them based on results — it only checks results against them.

Two things are produced:

* :func:`compare_graders` runs :func:`~mechgrader.eval.harness.run_eval` for each
  injected grader (typically ``baseline`` = RDKit-only and ``ai`` = the AI rubric)
  over the same held-out split, and renders the required comparison table.
* :func:`evaluate_cutoffs` turns two metrics dicts into a PASS/FAIL verdict:
  the AI grader must clear the absolute cutoffs **and** beat the baseline on
  accuracy, partial-credit correlation, and wrong-grade rate — all three.
"""

from __future__ import annotations

from typing import Optional

from .harness import GraderFn, run_eval

# --------------------------------------------------------------------------- #
# PRE-REGISTERED cutoffs (see PREREGISTERED.md). Do not tune to results.
# --------------------------------------------------------------------------- #
PREREGISTERED: dict = {
    "min_heldout_agreement": 0.85,  # AI must agree with the human >= 85% of the time
    "max_wrong_grade_rate": 0.05,  # AI confidently-wrong rate must be <= 5%
    # The AI grader must strictly beat the RDKit-only baseline on each of these:
    "ai_must_beat_baseline_on": ("agreement", "score_pearson", "wrong_grade_rate"),
    "pass_cutoff": 70,
    "clearly_correct_at": 90,
}

# Metrics where a *higher* number is better vs. where *lower* is better.
_HIGHER_IS_BETTER = {"agreement", "accuracy", "score_pearson", "score_spearman"}
_LOWER_IS_BETTER = {"wrong_grade_rate", "mae"}


def compare_graders(
    gold_items: list[dict],
    graders: dict[str, GraderFn],
    *,
    seed: int = 0,
    split: str = "heldout",
    bootstrap: int = 1000,
) -> dict:
    """Run each named grader over the same split and collect their metrics.

    ``graders`` maps a display name (e.g. ``"baseline"``, ``"ai"``) to a
    ``grader_fn``. Returns ``{"metrics": {name: run_eval(...)}, "split": ...}``.
    """
    metrics = {
        name: run_eval(gold_items, fn, seed=seed, split=split, bootstrap=bootstrap)
        for name, fn in graders.items()
    }
    return {"split": split, "seed": seed, "metrics": metrics}


def _fmt(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def format_table(metrics_by_name: dict[str, dict]) -> str:
    """Render the required baseline-vs-AI markdown table from run_eval outputs."""
    header = (
        "| Grader | n | Agreement (acc.) | Wrong-grade rate | Pearson | Spearman | MAE |\n"
        "| --- | --- | --- | --- | --- | --- | --- |"
    )
    rows = [header]
    for name, m in metrics_by_name.items():
        rows.append(
            "| {name} | {n} | {agr} | {wrong} | {pear} | {spear} | {mae} |".format(
                name=name,
                n=m.get("n_items", 0),
                agr=_fmt(m.get("agreement")),
                wrong=_fmt(m.get("wrong_grade_rate")),
                pear=_fmt(m.get("score_pearson")),
                spear=_fmt(m.get("score_spearman")),
                mae=_fmt(m.get("mae")),
            )
        )
    return "\n".join(rows)


def _beats(metric: str, ai_val: Optional[float], base_val: Optional[float]) -> tuple[bool, str]:
    """Did AI strictly beat baseline on ``metric``? Undefined values never 'win'."""
    if ai_val is None:
        return False, f"AI {metric} is undefined (n/a) — cannot claim a win"
    if base_val is None:
        # Baseline undefined (e.g. constant scores => no correlation). We do not
        # award the AI a correlation "win" against an undefined baseline; that
        # would be comparing to nothing. Require both defined to claim a beat.
        return False, f"baseline {metric} is undefined (n/a) — comparison not meaningful"
    if metric in _LOWER_IS_BETTER:
        return (ai_val < base_val), f"AI {metric} {ai_val:.3f} vs baseline {base_val:.3f} (lower is better)"
    return (ai_val > base_val), f"AI {metric} {ai_val:.3f} vs baseline {base_val:.3f} (higher is better)"


def evaluate_cutoffs(
    baseline_metrics: dict,
    ai_metrics: dict,
    prereg: dict = PREREGISTERED,
) -> dict:
    """Check AI metrics against the pre-registered cutoffs + the baseline.

    Returns ``{"passed": bool, "checks": [{name, passed, detail}], ...}``. The
    overall verdict passes only if **every** check passes.
    """
    checks: list[dict] = []

    agr = ai_metrics.get("agreement")
    ok = agr is not None and agr >= prereg["min_heldout_agreement"]
    checks.append(
        {
            "name": "absolute:agreement",
            "passed": bool(ok),
            "detail": f"AI agreement {_fmt(agr)} >= {prereg['min_heldout_agreement']} (pre-registered)",
        }
    )

    wgr = ai_metrics.get("wrong_grade_rate")
    ok = wgr is not None and wgr <= prereg["max_wrong_grade_rate"]
    checks.append(
        {
            "name": "absolute:wrong_grade_rate",
            "passed": bool(ok),
            "detail": f"AI wrong-grade rate {_fmt(wgr)} <= {prereg['max_wrong_grade_rate']} (pre-registered)",
        }
    )

    for metric in prereg["ai_must_beat_baseline_on"]:
        won, detail = _beats(metric, ai_metrics.get(metric), baseline_metrics.get(metric))
        checks.append({"name": f"beats_baseline:{metric}", "passed": bool(won), "detail": detail})

    passed = all(c["passed"] for c in checks)
    return {
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "checks": checks,
        "prereg": prereg,
    }


def format_report(comparison: dict, verdict: Optional[dict] = None) -> str:
    """Human-readable report: the table, then (if given) the cutoff verdict."""
    lines = [
        "Held-out evaluation (split = {}, seed = {}).".format(
            comparison.get("split"), comparison.get("seed")
        ),
        "",
        format_table(comparison["metrics"]),
    ]
    if verdict is not None:
        lines += ["", "Pre-registered cutoff check (fixed before results):"]
        for c in verdict["checks"]:
            mark = "PASS" if c["passed"] else "FAIL"
            lines.append(f"  [{mark}] {c['name']}: {c['detail']}")
        lines.append("")
        lines.append(f"Overall: {verdict['verdict']}")
    return "\n".join(lines)
