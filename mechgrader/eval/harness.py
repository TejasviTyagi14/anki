"""Seeded, grader-agnostic evaluation harness + the metrics it computes.

The public entry point is :func:`run_eval`. It takes a gold set (a list of
items — see ``data/gold_mechanisms/README.md``) and an injected grader callable,
runs the grader over the **held-out** split, and returns a metrics dict.

Design rules (all load-bearing for honesty):

* **stdlib only.** No RDKit, no API key, no numpy/pandas. The grader is injected,
  so the metrics can be tested with canned score functions.
* **Deterministic.** Items are processed in sorted-by-id order; the only source
  of randomness is the bootstrap confidence interval, which is seeded via
  ``seed`` so re-runs are bit-for-bit identical.
* **Held-out only.** ``run_eval`` filters to ``split == "heldout"`` by default.
  There is deliberately no code path that fits or tunes anything on this split.

Metrics returned (per grader), all vs. the human-assigned grade:

* ``agreement`` (a.k.a. ``accuracy``) — fraction of items where the grader's
  pass/fail verdict matches the human's (human passes iff ``human_grade >=
  PASS_CUTOFF``).
* ``wrong_grade_rate`` — the *confidently wrong* rate: the grader said **pass**
  but the human failed, **or** the grader said **fail** but the human marked the
  attempt clearly correct (``human_grade >= CLEARLY_CORRECT``). This is the
  metric a fabricated grader would blow.
* ``score_pearson`` / ``score_spearman`` — partial-credit correlation between the
  grader's 0-100 score and the human grade. ``None`` when a series has no
  variance (undefined correlation is reported as ``None``, never faked as 0/1).
* ``mae`` — mean absolute error of the predicted score vs. the human grade.
* ``confusion`` (tp/tn/fp/fn, pass = positive) and the explicit ``wrong_grades``
  list, so every wrong grade is traceable to an item id.
* ``agreement_ci95`` / ``wrong_grade_rate_ci95`` — seeded bootstrap 95% CIs.
"""

from __future__ import annotations

import glob
import json
import math
import os
import random
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

# A grader is any callable (attempt_mechanism, reference_mechanism) -> grade dict
# carrying at least a numeric "score" (0-100) and/or a bool "passed".
GraderFn = Callable[[dict, dict], dict]

# Pass line. Kept equal to the deterministic grader's PASS_THRESHOLD (70/100) so
# "the grader passed it" and "the human passed it" mean the same thing.
PASS_CUTOFF = 70

# A human grade at/above this is treated as "clearly correct" — failing such an
# attempt is a confidently-wrong grade (one half of the wrong-grade rate).
CLEARLY_CORRECT = 90

# Default location of the gold set (repo_root/data/gold_mechanisms).
GOLD_DIR = Path(__file__).resolve().parents[2] / "data" / "gold_mechanisms"

# The controlled vocabulary of author variant labels + their defensible grade
# bands (used by validate_gold_item so a mislabeled grade is caught). See the
# rubric in data/gold_mechanisms/README.md.
LABEL_GRADE_BANDS: dict[str, tuple[int, int]] = {
    "correct": (95, 100),
    "valid-alternative-route": (90, 99),
    "one-arrow-wrong": (70, 85),
    "right-product-unbalanced": (45, 65),
    "wrong-intermediate": (30, 50),
    "wrong-product": (10, 25),
    "valence-invalid": (0, 10),
}


# --------------------------------------------------------------------------- #
# stdlib statistics (implemented here so the harness needs nothing but math)
# --------------------------------------------------------------------------- #
def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    """Pearson correlation of two equal-length series, or ``None`` if undefined.

    Undefined (returned as ``None``, never fabricated) when there are < 2 points
    or either series has zero variance — e.g. a grader that outputs a constant
    score has no linear relationship to define.
    """
    if len(xs) != len(ys):
        raise ValueError("pearson: series must be the same length")
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0.0 or syy <= 0.0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return _clamp(sxy / math.sqrt(sxx * syy), -1.0, 1.0)


def _rankdata(vals: list[float]) -> list[float]:
    """1-based ranks with ties resolved by their average rank (fractional)."""
    order = sorted(range(len(vals)), key=lambda i: vals[i])
    ranks = [0.0] * len(vals)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # positions i..j share this average rank
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def spearman(xs: list[float], ys: list[float]) -> Optional[float]:
    """Spearman rank correlation (Pearson on average-tied ranks), or ``None``."""
    if len(xs) != len(ys):
        raise ValueError("spearman: series must be the same length")
    if len(xs) < 2:
        return None
    return pearson(_rankdata(xs), _rankdata(ys))


def _percentile(sorted_vals: list[float], q: float) -> Optional[float]:
    """Linear-interpolation percentile of an already-sorted list (q in [0,100])."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * (q / 100.0)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[int(pos)]
    frac = pos - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


# --------------------------------------------------------------------------- #
# reading a grade dict / a gold item
# --------------------------------------------------------------------------- #
def extract_score(grade: Any) -> int:
    """Pull a 0-100 integer score out of a grade dict (clamped).

    Accepts a dict with ``score``/``grade``/``value``, or a bare number/bool.
    A missing score is treated as 0 (not fabricated up).
    """
    if isinstance(grade, bool):
        return 100 if grade else 0
    if isinstance(grade, (int, float)):
        return int(_clamp(round(float(grade)), 0, 100))
    if isinstance(grade, dict):
        for key in ("score", "grade", "value"):
            if key in grade and isinstance(grade[key], (int, float)) and not isinstance(grade[key], bool):
                return int(_clamp(round(float(grade[key])), 0, 100))
    return 0


def extract_pass(grade: Any, *, pass_cutoff: int = PASS_CUTOFF) -> bool:
    """Pull a pass/fail verdict from a grade dict.

    Prefers an explicit ``passed``/``pass``/``correct`` bool; otherwise derives
    it from the score (``score >= pass_cutoff``).
    """
    if isinstance(grade, dict):
        for key in ("passed", "pass", "correct", "is_correct"):
            if key in grade and isinstance(grade[key], bool):
                return grade[key]
    return extract_score(grade) >= pass_cutoff


def human_grade(item: dict) -> float:
    """The item's human-assigned grade as a float in [0, 100]."""
    g = item.get("human_grade")
    if not isinstance(g, (int, float)) or isinstance(g, bool):
        raise ValueError(f"item {item.get('id')!r}: human_grade must be a number, got {g!r}")
    # Accept 0-1 or 0-100 (README allows either); normalise to 0-100.
    g = float(g)
    if 0.0 <= g <= 1.0 and not float(g).is_integer():
        g *= 100.0
    return _clamp(g, 0.0, 100.0)


# --------------------------------------------------------------------------- #
# the eval
# --------------------------------------------------------------------------- #
def _bootstrap_ci(
    per_item_correct: list[int],
    per_item_wrong: list[int],
    *,
    seed: int,
    resamples: int,
) -> tuple[Optional[list[float]], Optional[list[float]]]:
    """Seeded bootstrap 95% CIs for agreement and wrong-grade rate.

    Deterministic given ``seed``: same inputs + seed => identical intervals.
    Returns ``(agreement_ci, wrong_grade_ci)``; each is ``[lo, hi]`` or ``None``.
    """
    n = len(per_item_correct)
    if n == 0 or resamples <= 0:
        return None, None
    rng = random.Random(seed)
    agreements: list[float] = []
    wrongs: list[float] = []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        agreements.append(sum(per_item_correct[i] for i in idx) / n)
        wrongs.append(sum(per_item_wrong[i] for i in idx) / n)
    agreements.sort()
    wrongs.sort()
    return (
        [round(_percentile(agreements, 2.5), 6), round(_percentile(agreements, 97.5), 6)],
        [round(_percentile(wrongs, 2.5), 6), round(_percentile(wrongs, 97.5), 6)],
    )


def run_eval(
    gold_items: Iterable[dict],
    grader_fn: GraderFn,
    *,
    seed: int = 0,
    split: str = "heldout",
    pass_cutoff: int = PASS_CUTOFF,
    clearly_correct: int = CLEARLY_CORRECT,
    bootstrap: int = 1000,
) -> dict:
    """Run ``grader_fn`` over the ``split`` items and return the metrics dict.

    Parameters
    ----------
    gold_items : iterable of gold items (dicts with ``reference``, ``attempt``,
        ``human_grade``, ``split`` — see ``data/gold_mechanisms/README.md``).
    grader_fn : ``(attempt, reference) -> grade`` where ``grade`` is a dict with
        a numeric ``score`` and/or a bool ``passed`` (or a bare number/bool).
    seed : seeds the bootstrap CI so runs are reproducible.
    split : which split to evaluate; defaults to ``"heldout"``. **Never** call
        this with ``"train"`` for a reported number — that would be fitting on
        the same data used to design the grader.
    pass_cutoff : score at/above which a verdict counts as a pass.
    clearly_correct : human grade at/above which an attempt is "clearly correct"
        (failing it is a confidently-wrong grade).
    bootstrap : number of seeded bootstrap resamples for the CIs (0 to skip).

    The metrics are computed only over the selected split; there is no code path
    that touches any other split's grades.
    """
    items = [it for it in gold_items if it.get("split") == split]
    # Deterministic order regardless of input ordering.
    items.sort(key=lambda it: str(it.get("id", "")))

    evaluated_ids: list[str] = []
    predicted_scores: list[float] = []
    human_grades: list[float] = []
    per_item: list[dict] = []
    wrong_grades: list[dict] = []
    per_item_correct: list[int] = []  # 1 if pass/fail agrees with human
    per_item_wrong: list[int] = []  # 1 if confidently wrong
    tp = tn = fp = fn = 0

    for item in items:
        item_id = str(item.get("id", ""))
        grade = grader_fn(item.get("attempt"), item.get("reference"))
        pscore = extract_score(grade)
        ppass = extract_pass(grade, pass_cutoff=pass_cutoff)
        hgrade = human_grade(item)
        hpass = hgrade >= pass_cutoff
        hclear = hgrade >= clearly_correct

        evaluated_ids.append(item_id)
        predicted_scores.append(float(pscore))
        human_grades.append(hgrade)

        agrees = ppass == hpass
        per_item_correct.append(1 if agrees else 0)
        if ppass and hpass:
            tp += 1
        elif (not ppass) and (not hpass):
            tn += 1
        elif ppass and not hpass:
            fp += 1
        else:
            fn += 1

        # Confidently wrong: passed a human-fail, or failed a clearly-correct.
        kind = None
        if ppass and not hpass:
            kind = "false_pass"  # graded pass, human failed it
        elif (not ppass) and hclear:
            kind = "false_fail"  # graded fail, human marked it clearly correct
        per_item_wrong.append(1 if kind else 0)
        if kind:
            wrong_grades.append(
                {
                    "id": item_id,
                    "kind": kind,
                    "human_grade": hgrade,
                    "predicted_score": pscore,
                    "predicted_pass": ppass,
                }
            )

        per_item.append(
            {
                "id": item_id,
                "reaction_type": item.get("reaction_type"),
                "human_grade": hgrade,
                "human_pass": hpass,
                "predicted_score": pscore,
                "predicted_pass": ppass,
                "agrees": agrees,
            }
        )

    n = len(evaluated_ids)
    agreement = (sum(per_item_correct) / n) if n else None
    wrong_grade_rate = (sum(per_item_wrong) / n) if n else None
    mae = (sum(abs(p - h) for p, h in zip(predicted_scores, human_grades)) / n) if n else None
    agr_ci, wrong_ci = _bootstrap_ci(
        per_item_correct, per_item_wrong, seed=seed, resamples=bootstrap
    )

    return {
        "split": split,
        "seed": seed,
        "pass_cutoff": pass_cutoff,
        "clearly_correct_at": clearly_correct,
        "n_items": n,
        "evaluated_ids": evaluated_ids,
        "agreement": agreement,
        "accuracy": agreement,  # alias: pass/fail classification accuracy
        "wrong_grade_rate": wrong_grade_rate,
        "score_pearson": pearson(predicted_scores, human_grades) if n else None,
        "score_spearman": spearman(predicted_scores, human_grades) if n else None,
        "mae": mae,
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "n_wrong_grades": len(wrong_grades),
        "wrong_grades": wrong_grades,
        "agreement_ci95": agr_ci,
        "wrong_grade_rate_ci95": wrong_ci,
        "per_item": per_item,
    }


# --------------------------------------------------------------------------- #
# gold-set loading + validation (stdlib json; no SMILES parsing here)
# --------------------------------------------------------------------------- #
def _coerce_items(obj: Any) -> list[dict]:
    """Turn a loaded JSON blob into a list of item dicts.

    Accepts a list of items, a ``{"items": [...]}`` wrapper, or a single item.
    """
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    if isinstance(obj, dict):
        if isinstance(obj.get("items"), list):
            return [x for x in obj["items"] if isinstance(x, dict)]
        return [obj]
    return []


def load_gold_items(path: Optional[os.PathLike | str] = None) -> list[dict]:
    """Load every gold item from ``path`` (a file or directory).

    A directory is scanned for ``*.json`` (README/registry files ignored); each
    file may hold a single item, a list of items, or an ``{"items": [...]}``
    wrapper. Items are returned sorted by ``id`` for deterministic iteration.
    """
    target = Path(path) if path is not None else GOLD_DIR
    files: list[Path]
    if target.is_dir():
        files = sorted(Path(p) for p in glob.glob(str(target / "*.json")))
    elif target.is_file():
        files = [target]
    else:
        raise FileNotFoundError(f"gold path not found: {target}")

    items: list[dict] = []
    for fp in files:
        with open(fp, encoding="utf-8") as fh:
            items.extend(_coerce_items(json.load(fh)))
    items.sort(key=lambda it: str(it.get("id", "")))
    return items


def _is_mechanism(obj: Any) -> bool:
    """Shape check for a mechanism dict (does NOT parse SMILES)."""
    if not isinstance(obj, dict):
        return False
    steps = obj.get("steps")
    if not isinstance(steps, list) or not steps:
        return False
    for step in steps:
        if not isinstance(step, dict):
            return False
        for field in ("reactants", "products"):
            seq = step.get(field)
            if not isinstance(seq, list) or not seq:
                return False
            if not all(isinstance(s, str) and s.strip() for s in seq):
                return False
        if not isinstance(step.get("arrows", []), list):
            return False
    return True


def validate_gold_item(item: dict) -> list[str]:
    """Return a list of problems with a gold item (empty list == valid).

    Checks the schema/shape and — importantly for honesty — that each grade sits
    inside the defensible band for its variant label (so a mislabeled or
    inflated grade is caught here rather than silently trusted).
    """
    problems: list[str] = []
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        problems.append("missing/empty 'id'")
    if not isinstance(item.get("reaction_type"), str) or not item.get("reaction_type", "").strip():
        problems.append(f"{item_id}: missing 'reaction_type'")

    source_ref = item.get("source_ref")
    if not isinstance(source_ref, str) or "#" not in source_ref or source_ref.startswith("#"):
        problems.append(f"{item_id}: 'source_ref' must look like '<source_id>#<locator>'")

    if not _is_mechanism(item.get("reference")):
        problems.append(f"{item_id}: 'reference' is not a well-shaped mechanism")
    if not _is_mechanism(item.get("attempt")):
        problems.append(f"{item_id}: 'attempt' is not a well-shaped mechanism")

    grade = item.get("human_grade")
    if not isinstance(grade, (int, float)) or isinstance(grade, bool):
        problems.append(f"{item_id}: 'human_grade' must be a number")
        grade = None
    else:
        norm = human_grade(item)
        if not (0.0 <= norm <= 100.0):
            problems.append(f"{item_id}: 'human_grade' {norm} out of range 0-100")

    labels = item.get("human_labels")
    if not isinstance(labels, list) or not labels or not all(isinstance(x, str) for x in labels):
        problems.append(f"{item_id}: 'human_labels' must be a non-empty list of strings")
        labels = []

    if item.get("split") not in ("train", "heldout"):
        problems.append(f"{item_id}: 'split' must be 'train' or 'heldout'")

    # Grade must fall in the band defensible for at least one of its variant
    # labels (guards against an inflated/mislabeled reference grade).
    if grade is not None and labels:
        norm = human_grade(item)
        known = [lb for lb in labels if lb in LABEL_GRADE_BANDS]
        if known and not any(LABEL_GRADE_BANDS[lb][0] <= norm <= LABEL_GRADE_BANDS[lb][1] for lb in known):
            bands = ", ".join(f"{lb}{LABEL_GRADE_BANDS[lb]}" for lb in known)
            problems.append(f"{item_id}: grade {norm} outside the band(s) for its label(s): {bands}")

    return problems


def split_counts(items: Iterable[dict]) -> dict[str, int]:
    """Count items per split (e.g. ``{"train": 16, "heldout": 12}``)."""
    counts: dict[str, int] = {}
    for it in items:
        counts[str(it.get("split"))] = counts.get(str(it.get("split")), 0) + 1
    return counts
