"""Analyze a single reaction step: what actually changed, and is it conserved?

Given a reactant and a product SMILES this module:

* builds an atom mapping between them (via maximum common substructure),
* detects which bonds were formed / broken / changed order,
* computes element and charge deltas (conservation checks),
* estimates the change in unsaturation.

Atom mapping via MCS is a heuristic. It can be ambiguous for symmetric molecules
and can under-map when the two structures are very different (a big change in one
"step"). ``mcs_coverage`` is reported so the grader can lower its confidence, and
this limitation is called out in the README.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from rdkit import Chem
from rdkit.Chem import rdFMCS, rdMolDescriptors

from .structure_service import StructureError, count_unsaturation

_HALIDES = {"F", "Cl", "Br", "I"}

# Very rough lexical hints that a reagent can donate a carbon. Used only to make
# conservation feedback more helpful; see caveats in the README.
_CARBON_REAGENT_HINTS = [
    "cn", "cyanide", "grignard", "mgbr", "mgcl", "mgi", "rli", "meli",
    "ome", "oet", "otbu", "obu", "methyl", "ethyl", "alkyl", "acetyl",
    "ch3", "ch2", "co2", "co ", "ester", "acetate", "malonate",
]


@dataclass
class BondChange:
    """A bond that appears or disappears between reactant and product."""

    element_a: str
    element_b: str
    order: int

    def key(self) -> tuple[str, str, int]:
        a, b = sorted((self.element_a, self.element_b))
        return (a, b, self.order)

    def __str__(self) -> str:
        a, b = sorted((self.element_a, self.element_b))
        symbol = {1: "-", 2: "=", 3: "#"}.get(self.order, "-")
        return f"{a}{symbol}{b}"


@dataclass
class TransformationDiff:
    reactant_smiles: str
    product_smiles: str
    reactant_formula: str
    product_formula: str
    element_delta: dict[str, int]  # product - reactant (includes H)
    charge_delta: int
    delta_unsaturation: int
    bonds_broken: list[BondChange] = field(default_factory=list)
    bonds_formed: list[BondChange] = field(default_factory=list)
    order_changes: list[tuple[BondChange, BondChange]] = field(default_factory=list)
    added_atoms: list[str] = field(default_factory=list)  # elements in product only
    removed_atoms: list[str] = field(default_factory=list)  # elements in reactant only
    mcs_coverage: float = 0.0
    mapped: bool = False

    # --- derived conservation booleans ---
    @property
    def is_isomerization(self) -> bool:
        return not self.element_delta and self.charge_delta == 0

    @property
    def charge_balanced(self) -> bool:
        return self.charge_delta == 0

    @property
    def carbon_delta(self) -> int:
        return self.element_delta.get("C", 0)

    def describe(self) -> list[str]:
        """Human-readable summary of the changes."""
        out: list[str] = []
        for b in self.bonds_broken:
            out.append(f"broke {b} bond")
        for b in self.bonds_formed:
            out.append(f"formed {b} bond")
        for before, after in self.order_changes:
            out.append(f"changed {before} -> {after}")
        if self.delta_unsaturation:
            sign = "+" if self.delta_unsaturation > 0 else ""
            out.append(f"unsaturation {sign}{self.delta_unsaturation}")
        if self.removed_atoms:
            out.append("lost atoms: " + ", ".join(sorted(self.removed_atoms)))
        if self.added_atoms:
            out.append("gained atoms: " + ", ".join(sorted(self.added_atoms)))
        return out

    def conservation_errors(self, reagents: Optional[list[str]] = None) -> list[str]:
        """Flag atom-count problems that no reagent can explain.

        HEURISTIC (may produce false positives/negatives):
        * losing carbons implies fragmentation -> almost always a drawing error;
        * gaining carbons is only plausible if a reagent can donate carbon.
        Charge changes are reported as warnings by the grader, not here.
        """
        errors: list[str] = []
        cdelta = self.carbon_delta
        if cdelta < 0:
            errors.append(
                f"atom count not conserved: product lost {-cdelta} carbon(s) "
                "(carbon skeletons don't fragment in a normal step)"
            )
        elif cdelta > 0 and not _reagents_supply_carbon(reagents or []):
            errors.append(
                f"atom count not conserved: product gained {cdelta} carbon(s) "
                "but no reagent appears to supply carbon"
            )
        return errors


def _reagents_supply_carbon(reagents: list[str]) -> bool:
    joined = " ".join(reagents).lower()
    if any(hint in joined for hint in _CARBON_REAGENT_HINTS):
        return True
    # A reagent token containing a capital C followed by lower-case/(digit) often
    # indicates an organic reagent (CH3I, CO2, PhCH2Br...).
    return bool(re.search(r"C[H(]|C\d|CH\d", " ".join(reagents)))


def element_counts(mol: Chem.Mol) -> dict[str, int]:
    """Element -> count, including implicit + explicit hydrogens."""
    counts: dict[str, int] = {}
    h = 0
    for atom in mol.GetAtoms():
        sym = atom.GetSymbol()
        if sym == "H":
            h += 1
        else:
            counts[sym] = counts.get(sym, 0) + 1
        h += atom.GetTotalNumHs()
    if h:
        counts["H"] = counts.get("H", 0) + h
    return counts


def _bond_orders(mol: Chem.Mol) -> dict[frozenset, int]:
    work = Chem.Mol(mol)
    try:
        Chem.Kekulize(work, clearAromaticFlags=True)
    except Exception:
        pass
    orders: dict[frozenset, int] = {}
    for bond in work.GetBonds():
        key = frozenset((bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()))
        orders[key] = int(round(bond.GetBondTypeAsDouble()))
    return orders


def atom_map_via_mcs(reactant: Chem.Mol, product: Chem.Mol):
    """Return (mapping reactant_idx->product_idx, coverage) via MCS.

    Bonds are compared with ``CompareAny`` so the skeleton maps even when bond
    orders change (addition/elimination); order changes are detected afterwards.
    """
    result = rdFMCS.FindMCS(
        [reactant, product],
        atomCompare=rdFMCS.AtomCompare.CompareElements,
        bondCompare=rdFMCS.BondCompare.CompareAny,
        ringMatchesRingOnly=False,
        completeRingsOnly=False,
        matchValences=False,
        timeout=10,
    )
    if not result.smartsString or result.numAtoms == 0:
        return {}, 0.0
    query = Chem.MolFromSmarts(result.smartsString)
    if query is None:
        return {}, 0.0
    r_match = reactant.GetSubstructMatch(query)
    p_match = product.GetSubstructMatch(query)
    if not r_match or not p_match or len(r_match) != len(p_match):
        return {}, 0.0
    mapping = {r_match[i]: p_match[i] for i in range(len(r_match))}
    # Coverage relative to the smaller molecule, so adding a large group (e.g. a
    # Grignard) doesn't look like a low-overlap step.
    heavy = max(min(reactant.GetNumAtoms(), product.GetNumAtoms()), 1)
    coverage = len(mapping) / heavy
    return mapping, coverage


def analyze_transformation(reactant_smiles: str, product_smiles: str) -> TransformationDiff:
    reactant = Chem.MolFromSmiles(reactant_smiles)
    product = Chem.MolFromSmiles(product_smiles)
    if reactant is None:
        raise StructureError(f"invalid reactant SMILES: {reactant_smiles!r}")
    if product is None:
        raise StructureError(f"invalid product SMILES: {product_smiles!r}")

    r_counts = element_counts(reactant)
    p_counts = element_counts(product)
    element_delta: dict[str, int] = {}
    for el in set(r_counts) | set(p_counts):
        d = p_counts.get(el, 0) - r_counts.get(el, 0)
        if d:
            element_delta[el] = d

    diff = TransformationDiff(
        reactant_smiles=Chem.MolToSmiles(reactant),
        product_smiles=Chem.MolToSmiles(product),
        reactant_formula=rdMolDescriptors.CalcMolFormula(reactant),
        product_formula=rdMolDescriptors.CalcMolFormula(product),
        element_delta=element_delta,
        charge_delta=Chem.GetFormalCharge(product) - Chem.GetFormalCharge(reactant),
        delta_unsaturation=count_unsaturation(product) - count_unsaturation(reactant),
    )

    mapping, coverage = atom_map_via_mcs(reactant, product)
    diff.mcs_coverage = round(coverage, 3)
    diff.mapped = bool(mapping)
    if not mapping:
        return diff

    r_orders = _bond_orders(reactant)
    p_orders = _bond_orders(product)
    inv = {v: k for k, v in mapping.items()}

    # Reactant bonds: broken if they don't survive into the product. A bond to a
    # *removed* atom (a leaving group) counts as broken too.
    for bond in reactant.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        r_order = r_orders.get(frozenset((a, b)), 1)
        ea = reactant.GetAtomWithIdx(a).GetSymbol()
        eb = reactant.GetAtomWithIdx(b).GetSymbol()
        a_mapped, b_mapped = a in mapping, b in mapping
        if a_mapped and b_mapped:
            p_order = p_orders.get(frozenset((mapping[a], mapping[b])))
            if p_order is None:
                diff.bonds_broken.append(BondChange(ea, eb, r_order))
            elif p_order != r_order:
                diff.order_changes.append(
                    (BondChange(ea, eb, r_order), BondChange(ea, eb, p_order))
                )
        elif a_mapped != b_mapped:
            # bond from the surviving skeleton to a leaving atom -> broken
            diff.bonds_broken.append(BondChange(ea, eb, r_order))

    # Product bonds: formed if they had no counterpart in the reactant. A bond to
    # an *added* atom (incoming group) counts as formed too.
    for bond in product.GetBonds():
        a, b = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        p_order = p_orders.get(frozenset((a, b)), 1)
        ea = product.GetAtomWithIdx(a).GetSymbol()
        eb = product.GetAtomWithIdx(b).GetSymbol()
        a_in, b_in = a in inv, b in inv
        if a_in and b_in:
            if frozenset((inv[a], inv[b])) not in r_orders:
                diff.bonds_formed.append(BondChange(ea, eb, p_order))
        elif a_in != b_in:
            # bond from the surviving skeleton to an incoming atom -> formed
            diff.bonds_formed.append(BondChange(ea, eb, p_order))

    diff.removed_atoms = [
        reactant.GetAtomWithIdx(i).GetSymbol()
        for i in range(reactant.GetNumAtoms())
        if i not in mapping
    ]
    diff.added_atoms = [
        product.GetAtomWithIdx(i).GetSymbol()
        for i in range(product.GetNumAtoms())
        if i not in inv
    ]
    return diff


def structural_diff(smiles_a: str, smiles_b: str) -> dict:
    """Locate the atoms/bonds that differ between two structures (by index).

    Read-only display helper (used to highlight *exactly* where a drawn structure
    differs from the expected one). Indices are into each molecule's own RDKit
    numbering of the given SMILES, which matches :mod:`chemgrader.depiction`.
    """
    a = Chem.MolFromSmiles(smiles_a)
    b = Chem.MolFromSmiles(smiles_b)
    if a is None:
        raise StructureError(f"invalid SMILES: {smiles_a!r}")
    if b is None:
        raise StructureError(f"invalid SMILES: {smiles_b!r}")

    mapping, coverage = atom_map_via_mcs(a, b)
    inv = {v: k for k, v in mapping.items()}
    ao, bo = _bond_orders(a), _bond_orders(b)

    changed_atoms_a = [i for i in range(a.GetNumAtoms()) if i not in mapping]
    changed_atoms_b = [i for i in range(b.GetNumAtoms()) if i not in inv]

    changed_bonds_a: list[list[int]] = []
    for bond in a.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if i in mapping and j in mapping:
            if bo.get(frozenset((mapping[i], mapping[j]))) != ao.get(frozenset((i, j))):
                changed_bonds_a.append([i, j])
        else:
            changed_bonds_a.append([i, j])

    changed_bonds_b: list[list[int]] = []
    for bond in b.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        if i in inv and j in inv:
            if ao.get(frozenset((inv[i], inv[j]))) != bo.get(frozenset((i, j))):
                changed_bonds_b.append([i, j])
        else:
            changed_bonds_b.append([i, j])

    return {
        "changed_atoms_a": changed_atoms_a,
        "changed_atoms_b": changed_atoms_b,
        "changed_bonds_a": changed_bonds_a,
        "changed_bonds_b": changed_bonds_b,
        "coverage": round(coverage, 3),
        "same": not (changed_atoms_a or changed_atoms_b or changed_bonds_a or changed_bonds_b),
    }
