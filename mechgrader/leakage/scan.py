"""Near-duplicate / leakage detection over mechanisms (RDKit).

A mechanism's identity is the multiset of its molecular species (all reactants +
products across steps), canonicalized by RDKit. Two mechanisms are flagged as a
near-duplicate when:

* their canonical-SMILES species sets are identical, or
* their InChIKey species sets are identical, or
* a strong fraction of one's species have a Morgan-fingerprint Tanimoto >= a
  threshold match in the other (fuzzy near-dup: e.g. the same reaction on a
  slightly different substrate).

`scan_gold` checks that no held-out gold item near-duplicates any training /
few-shot / calibration input (and that no item is duplicated across splits).
"""

from __future__ import annotations

from typing import Any, Optional

from rdkit import Chem, DataStructs, RDLogger
from rdkit.Chem import AllChem, inchi

RDLogger.DisableLog("rdApp.*")

MORGAN_RADIUS = 2
MORGAN_BITS = 2048
DEFAULT_TANIMOTO = 0.90
# Fraction of a mechanism's species that must have a >= Tanimoto match in the
# other for a fuzzy near-duplicate flag.
SPECIES_MATCH_FRACTION = 0.80


def _species_smiles(mech: dict) -> list[str]:
    out: list[str] = []
    for step in (mech or {}).get("steps", []):
        for key in ("reactants", "products"):
            for s in step.get(key, []) or []:
                if isinstance(s, str) and s.strip():
                    out.append(s)
    return out


def _canonical(smiles: str) -> Optional[tuple[str, Optional[str], Any]]:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None
    # Strip atom-map numbers so identity ignores mapping choices.
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    canonical = Chem.MolToSmiles(mol)
    try:
        key = inchi.MolToInchiKey(mol) or None
    except Exception:
        key = None
    fp = AllChem.GetMorganFingerprintAsBitVect(mol, MORGAN_RADIUS, nBits=MORGAN_BITS)
    return canonical, key, fp


def _profile(mech: dict) -> dict:
    cans: set[str] = set()
    keys: set[str] = set()
    fps: list[Any] = []
    invalid = 0
    for s in _species_smiles(mech):
        r = _canonical(s)
        if r is None:
            invalid += 1
            continue
        can, key, fp = r
        cans.add(can)
        if key:
            keys.add(key)
        fps.append(fp)
    return {"cans": cans, "inchikeys": keys, "fps": fps, "invalid": invalid}


def _max_tanimoto(fp: Any, others: list[Any]) -> float:
    best = 0.0
    for o in others:
        t = DataStructs.TanimotoSimilarity(fp, o)
        if t > best:
            best = t
    return best


def mechanisms_near_dup(
    a: dict, b: dict, *, tanimoto: float = DEFAULT_TANIMOTO
) -> tuple[bool, str]:
    """Return (is_near_dup, reason) for two mechanisms."""
    pa, pb = _profile(a), _profile(b)
    if pa["cans"] and pa["cans"] == pb["cans"]:
        return True, "identical canonical-SMILES species set"
    if pa["inchikeys"] and pa["inchikeys"] == pb["inchikeys"]:
        return True, "identical InChIKey species set"
    if pa["fps"] and pb["fps"]:
        # Symmetric: flag if EITHER mechanism has a strong fraction of its species
        # matched in the other (so the relation is order-independent and grouping
        # agrees with the held-out->training scan).
        matched_a = sum(1 for fa in pa["fps"] if _max_tanimoto(fa, pb["fps"]) >= tanimoto)
        matched_b = sum(1 for fb in pb["fps"] if _max_tanimoto(fb, pa["fps"]) >= tanimoto)
        frac = max(matched_a / len(pa["fps"]), matched_b / len(pb["fps"]))
        if frac >= SPECIES_MATCH_FRACTION:
            return True, f"{frac:.0%} of species have a Tanimoto>={tanimoto} match"
    return False, "no near-duplicate"


def _reference_of(item: dict) -> dict:
    """The reference mechanism (the reaction under test) is what could leak."""
    return item.get("reference") or {}


def scan_gold(
    gold_items: list[dict],
    *,
    extra_training_inputs: Optional[list[dict]] = None,
    tanimoto: float = DEFAULT_TANIMOTO,
    split_field: str = "split",
    heldout: str = "heldout",
    train: str = "train",
) -> dict:
    """Check that no held-out item near-duplicates a training/few-shot/calibration
    input, and that no item id appears in more than one split.

    ``extra_training_inputs`` is any list of mechanism dicts (few-shot examples,
    calibration mechanisms) that must NOT contain a held-out reaction.

    Returns ``{ok, n_heldout, n_train, leaks: [...], duplicate_ids: [...]}``.
    """
    heldout_items = [it for it in gold_items if it.get(split_field) == heldout]
    train_items = [it for it in gold_items if it.get(split_field) == train]

    # Training-side inputs a held-out reaction must never appear in.
    train_refs: list[tuple[str, dict]] = [
        (str(it.get("id", f"train#{i}")), _reference_of(it))
        for i, it in enumerate(train_items)
    ]
    for j, mech in enumerate(extra_training_inputs or []):
        train_refs.append((f"extra#{j}", mech if "steps" in mech else {"steps": []}))

    leaks: list[dict] = []
    for it in heldout_items:
        hid = str(it.get("id", "?"))
        href = _reference_of(it)
        for tid, tref in train_refs:
            dup, reason = mechanisms_near_dup(href, tref, tanimoto=tanimoto)
            if dup:
                leaks.append({"heldout_id": hid, "training_id": tid, "reason": reason})

    # Any id present in more than one split is itself a leak.
    seen: dict[str, set] = {}
    for it in gold_items:
        seen.setdefault(str(it.get("id", "?")), set()).add(it.get(split_field))
    duplicate_ids = [i for i, splits in seen.items() if len(splits) > 1]

    return {
        "ok": not leaks and not duplicate_ids,
        "n_heldout": len(heldout_items),
        "n_train": len(train_items),
        "tanimoto": tanimoto,
        "leaks": leaks,
        "duplicate_ids": duplicate_ids,
    }
