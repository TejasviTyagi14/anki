"""Study-feature experiment (rubric Section 8): interleaving of mechanistically-
related reaction types vs blocked practice vs plain review.

HONESTY: real students can't be gathered in a week, so this is a SIMULATION with
an explicit, stated learner model, run as the fair three-arm test the rubric asks
for (same learners, same items, same time budget). The numbers reflect the
model's assumptions, NOT real students — the harness is ready to run on a real
cohort by swapping the simulated learner for logged review/grade data. The model
is deliberately NOT rigged to favor interleaving: interleaving trades a little
per-type consolidation (a switch cost) for cross-type discrimination, so it only
wins when confusability is high enough. A confusability sweep shows the null/
negative region too.
"""

from .study_feature import DEFAULTS, run_experiment, confusability_sweep

__all__ = ["DEFAULTS", "run_experiment", "confusability_sweep"]
