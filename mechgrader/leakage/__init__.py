"""Leakage / near-duplicate detection over mechanism datasets (rubric 7e).

Leaked test data zeros the score, so this must run and be clean. It flags any
held-out/gold item that also appears — or near-duplicates — in the training /
few-shot / calibration inputs, using RDKit: canonical SMILES + InChIKey (exact)
and Morgan-fingerprint Tanimoto (fuzzy).
"""

from .scan import (
    DEFAULT_TANIMOTO,
    mechanisms_near_dup,
    scan_gold,
)

__all__ = ["DEFAULT_TANIMOTO", "mechanisms_near_dup", "scan_gold"]
