"""Validate curved-arrow (electron-pushing) notation.

Arrow-pushing is optional on an edge. When provided, we check that the electron
flow is *consistent* with the structural change and doesn't obviously violate
valence/octet:

* every endpoint references a real atom/bond in the reactant;
* each arrow moves 1 (fishhook) or 2 (curved) electrons;
* the number of arrows is consistent with the count of bonds formed/broken;
* forming a bond onto an atom that is already valence-saturated (without also
  breaking one of its bonds) is flagged as an octet/valence violation.

This is a PARTIAL check: full electron bookkeeping (tracking every lone pair and
formal charge through the mechanism) is out of scope, so subtle errors can slip
through. Treated as warnings unless an endpoint is structurally invalid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rdkit import Chem

from .mechanisms import effective_broken, effective_formed
from .models import ArrowOp
from .transformation import TransformationDiff

# Neutral maximum bonding valence for common period-2 elements (+ H, halogens).
_MAX_VALENCE = {"C": 4, "N": 3, "O": 2, "F": 1, "Cl": 1, "Br": 1, "I": 1, "H": 1, "S": 6, "P": 5}


@dataclass
class ArrowReport:
    checked: bool
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Endpoint:
    kind: str  # "atom" | "bond" | "lp"
    atoms: tuple[int, ...]


def parse_endpoint(text: str) -> _Endpoint:
    raw = text.strip().lower()
    if ":" not in raw:
        raise ValueError(f"malformed arrow endpoint {text!r} (expected 'atom:i', 'bond:i-j', 'lp:i')")
    kind, rest = raw.split(":", 1)
    kind = kind.strip()
    if kind not in {"atom", "bond", "lp"}:
        raise ValueError(f"unknown endpoint kind {kind!r} in {text!r}")
    try:
        atoms = tuple(int(x) for x in rest.replace("_", "-").split("-") if x != "")
    except ValueError as exc:
        raise ValueError(f"bad atom index in {text!r}") from exc
    if kind == "bond" and len(atoms) != 2:
        raise ValueError(f"'bond' endpoint needs two atom indices, got {text!r}")
    if kind in {"atom", "lp"} and len(atoms) != 1:
        raise ValueError(f"'{kind}' endpoint needs one atom index, got {text!r}")
    return _Endpoint(kind, atoms)


def _atom_ok(mol: Chem.Mol, idx: int) -> bool:
    return 0 <= idx < mol.GetNumAtoms()


def _bond_exists(mol: Chem.Mol, i: int, j: int) -> bool:
    return mol.GetBondBetweenAtoms(i, j) is not None


def _current_valence(atom: Chem.Atom) -> int:
    return int(atom.GetTotalValence())


def validate_arrows(
    arrows: list[ArrowOp],
    reactant: Optional[Chem.Mol],
    diff: Optional[TransformationDiff] = None,
) -> ArrowReport:
    if not arrows:
        return ArrowReport(checked=False, ok=True)
    if reactant is None:
        return ArrowReport(checked=False, ok=True, warnings=["no reactant to validate arrows against"])

    errors: list[str] = []
    warnings: list[str] = []
    source_bond_count = 0
    target_bond_count = 0
    gained_bond_targets: list[int] = []

    for i, arrow in enumerate(arrows):
        tag = f"arrow #{i + 1}"
        if arrow.electrons not in (1, 2):
            warnings.append(f"{tag}: moves {arrow.electrons} electrons (expected 1 or 2)")
        try:
            src = parse_endpoint(arrow.source)
            dst = parse_endpoint(arrow.target)
        except ValueError as exc:
            errors.append(f"{tag}: {exc}")
            continue

        for ep, role in ((src, "source"), (dst, "target")):
            for a in ep.atoms:
                if not _atom_ok(reactant, a):
                    errors.append(f"{tag}: {role} atom index {a} out of range")
            if ep.kind == "bond" and len(ep.atoms) == 2 and all(_atom_ok(reactant, a) for a in ep.atoms):
                if not _bond_exists(reactant, ep.atoms[0], ep.atoms[1]):
                    errors.append(
                        f"{tag}: {role} bond {ep.atoms[0]}-{ep.atoms[1]} does not exist in the reactant"
                    )

        if src.kind == "bond":
            source_bond_count += 1
        if dst.kind == "bond":
            target_bond_count += 1
            gained_bond_targets.extend(dst.atoms)
        elif dst.kind == "atom":
            gained_bond_targets.extend(dst.atoms)

    # Octet / valence sanity check on atoms that gain a bond.
    for a in gained_bond_targets:
        if not _atom_ok(reactant, a):
            continue
        atom = reactant.GetAtomWithIdx(a)
        sym = atom.GetSymbol()
        cap = _MAX_VALENCE.get(sym)
        if cap is None:
            continue
        # If the atom is already at capacity and neutral, forming another bond
        # needs a bond to break at the same atom (an arrow leaving it).
        leaves_here = any(
            _safe_kind(arrow.source) == "bond" and a in _safe_atoms(arrow.source)
            for arrow in arrows
        )
        if _current_valence(atom) >= cap and atom.GetFormalCharge() <= 0 and not leaves_here:
            warnings.append(
                f"forming a bond onto atom {a} ({sym}) would exceed its normal "
                f"valence/octet ({cap}) with no bond breaking there"
            )

    # Cross-check arrow count vs. observed structural change.
    if diff is not None:
        n_broken = len(effective_broken(diff))
        n_formed = len(effective_formed(diff))
        if n_broken and source_bond_count < n_broken:
            warnings.append(
                f"{n_broken} bond(s) break but only {source_bond_count} arrow(s) "
                "originate from a bond"
            )
        if n_formed and target_bond_count == 0 and not gained_bond_targets:
            warnings.append(
                f"{n_formed} bond(s) form but no arrow points to where a bond forms"
            )

    return ArrowReport(checked=True, ok=not errors, errors=errors, warnings=warnings)


def _safe_kind(text: str) -> str:
    try:
        return parse_endpoint(text).kind
    except ValueError:
        return ""


def _safe_atoms(text: str) -> tuple[int, ...]:
    try:
        return parse_endpoint(text).atoms
    except ValueError:
        return ()
