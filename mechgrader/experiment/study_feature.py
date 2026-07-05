"""The fair three-arm study-feature simulation (pure stdlib, seeded).

Learner model (stated so the result is interpretable, not a black box):
- Reaction types are grouped into confusable families (SN1/SN2/E1/E2 are highly
  confusable; addition and aromatic families less so).
- Practicing a type raises its `skill` (log-odds, diminishing returns).
- INTERLEAVED practice within a family additionally raises the family's
  `discrimination` in [0,1]; blocked/plain practice does not.
- Interleaving pays a per-trial consolidation `switch_cost` (it feels harder).
- On a NOVEL MIXED-type test, P(correct) for a type T in family F is
  sigmoid(aptitude + skill[T] - confusability[F] * (1 - discrimination[F])).

So blocked practice → high skill but zero discrimination → confusion errors on a
mixed test; interleaving → slightly lower skill but high discrimination. The net
depends on `confusability`: at 0 interleaving *hurts* (only the switch cost
bites); at high confusability it *helps*. That crossover is what makes this a
fair test rather than a rigged one.
"""

from __future__ import annotations

import math
import random
import statistics

# Confusable families. Substitution/elimination is the classic orgo trap.
FAMILIES = {
    "substitution_elimination": ["SN1", "SN2", "E1", "E2"],
    "addition": ["electrophilic_addition", "carbonyl_addition"],
    "aromatic": ["EAS"],
}

DEFAULTS = dict(
    trials=120,            # equal time budget (practice trials) per learner
    learn_rate=0.18,       # approach rate toward the skill cap per focused trial
    skill_cap=2.5,         # max per-type skill (log-odds); gives diminishing returns
    switch_cost=0.35,      # fraction of skill gain LOST to interleaving's harder context
    disc_rate=0.06,        # discrimination gained per interleaved trial
    plain_efficiency=0.6,  # plain review builds mechanism skill less well (memory-only)
    confusability=1.6,     # orgo families are highly confusable (logit penalty)
    test_items_per_type=40,
    n_learners=200,
)


def _sigmoid(x: float) -> float:
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def _types() -> list[tuple[str, str]]:
    return [(t, fam) for fam, ts in FAMILIES.items() for t in ts]


def _run_arm(arm: str, aptitude: float, p: dict) -> float:
    """Train one learner under `arm`, then return expected mixed-test accuracy."""
    types = _types()
    n_types = len(types)
    trials_per_type = max(1, p["trials"] // n_types)

    skill = {t: 0.0 for t, _ in types}
    disc = {fam: 0.0 for fam in FAMILIES}
    cap = p["skill_cap"]

    def learn(t, rate):  # diminishing returns toward the cap
        skill[t] += rate * (cap - skill[t])

    if arm == "interleaved":
        # cycle through types within families -> every trial is a context switch
        for _ in range(trials_per_type):
            for t, fam in types:
                learn(t, p["learn_rate"] * (1.0 - p["switch_cost"]))
                disc[fam] += p["disc_rate"] * (1.0 - disc[fam])
    elif arm == "blocked":
        # all trials of a type together -> full consolidation, no discrimination
        for t, _fam in types:
            for _ in range(trials_per_type):
                learn(t, p["learn_rate"])
    elif arm == "plain":
        # plain review (unmodified Anki): memory-only, no mechanism structure
        for t, _fam in types:
            for _ in range(trials_per_type):
                learn(t, p["learn_rate"] * p["plain_efficiency"])
    else:
        raise ValueError(arm)

    # Novel MIXED-type test: expected accuracy over test items (no sampling noise;
    # the range across learners comes from aptitude variation).
    probs = []
    for t, fam in types:
        penalty = p["confusability"] * (1.0 - disc[fam])
        prob = _sigmoid(aptitude + skill[t] - penalty)
        probs.extend([prob] * p["test_items_per_type"])
    return statistics.fmean(probs)


def _cohort(seed: int, n: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.gauss(0.0, 0.5) for _ in range(n)]


def _summary(vals: list[float]) -> dict:
    vals = sorted(vals)
    n = len(vals)

    def pct(q):
        return vals[min(n - 1, int(q * (n - 1) + 0.5))]

    return {
        "mean": round(statistics.fmean(vals), 4),
        "range": {"low": round(pct(0.025), 4), "high": round(pct(0.975), 4)},
        "n": n,
    }


def run_experiment(seed: int = 0, params: dict | None = None) -> dict:
    """Run all three arms on the SAME learners/items/time budget. Returns per-arm
    mixed-test accuracy (mean + 95% range across learners) + a verdict."""
    p = {**DEFAULTS, **(params or {})}
    cohort = _cohort(seed, p["n_learners"])
    arms = {}
    for arm in ("interleaved", "blocked", "plain"):
        arms[arm] = _summary([_run_arm(arm, a, p) for a in cohort])

    inter = arms["interleaved"]["mean"]
    blocked = arms["blocked"]["mean"]
    delta = round(inter - blocked, 4)
    # Pre-registered primary metric: accuracy on novel mixed-type questions,
    # interleaving vs blocked, at equal study time.
    if delta > 0.01:
        verdict = "interleaving HELPED vs blocked (model, this confusability)"
    elif delta < -0.01:
        verdict = "interleaving HURT vs blocked (model)"
    else:
        verdict = "NULL: no meaningful difference (model)"
    return {
        "seed": seed,
        "params": p,
        "arms": arms,
        "primary_metric": "mixed-type novel-question accuracy",
        "interleaved_minus_blocked": delta,
        "verdict": verdict,
        "note": "SIMULATION with a stated learner model; not a claim about real students.",
    }


def confusability_sweep(seed: int = 0, levels=None, params: dict | None = None) -> list[dict]:
    """Show interleaved vs blocked across confusability — including where
    interleaving does NOT help (the fair-test evidence)."""
    levels = levels or [0.0, 0.5, 1.0, 1.6, 2.4]
    out = []
    for c in levels:
        r = run_experiment(seed, {**(params or {}), "confusability": c})
        out.append({
            "confusability": c,
            "interleaved": r["arms"]["interleaved"]["mean"],
            "blocked": r["arms"]["blocked"]["mean"],
            "delta": r["interleaved_minus_blocked"],
        })
    return out
