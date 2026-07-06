"""SMARTS-based functional-group detection.

Ordered so that more specific groups are listed before the generic groups they
would otherwise also match (e.g. carboxylic acid before hydroxyl). Detection
returns the set of names whose SMARTS match at least once.

These patterns are intentionally pragmatic, not exhaustive -- they cover the
functional groups that show up in MCAT-level organic chemistry. Extend the
``FUNCTIONAL_GROUPS`` list to teach the grader about more groups.
"""

from __future__ import annotations

from rdkit import Chem

# name -> SMARTS. Order matters for readability only; detection reports all hits.
FUNCTIONAL_GROUPS: list[tuple[str, str]] = [
    ("carboxylic_acid", "[CX3](=O)[OX2H1]"),
    ("acyl_halide", "[CX3](=[OX1])[F,Cl,Br,I]"),
    ("acid_anhydride", "[CX3](=[OX1])[OX2][CX3](=[OX1])"),
    ("ester", "[CX3](=[OX1])[OX2H0][#6]"),
    ("amide", "[NX3][CX3](=[OX1])"),
    ("nitrile", "[NX1]#[CX2]"),
    ("aldehyde", "[CX3H1](=O)[#6,H]"),
    ("ketone", "[#6][CX3](=O)[#6]"),
    ("enol", "[CX3]=[CX3][OX2H1]"),
    ("primary_alcohol", "[CX4H2][OX2H1]"),
    ("secondary_alcohol", "[CX4H1][OX2H1]"),
    ("tertiary_alcohol", "[CX4H0][OX2H1]"),
    ("alcohol", "[#6][OX2H1]"),
    ("phenol", "[c][OX2H1]"),
    ("ether", "[OD2]([#6])[#6]"),
    ("epoxide", "[OX2r3]1[#6r3][#6r3]1"),
    ("primary_amine", "[NX3;H2][#6]"),
    ("secondary_amine", "[NX3;H1]([#6])[#6]"),
    ("tertiary_amine", "[NX3;H0]([#6])([#6])[#6]"),
    ("amine", "[NX3;!$(NC=O)]"),
    ("thiol", "[#16X2H1]"),
    ("sulfide", "[#16X2H0]([#6])[#6]"),
    ("nitro", "[NX3](=O)=O"),
    ("alkyl_halide", "[CX4][F,Cl,Br,I]"),
    ("vinyl_aryl_halide", "[c,$([CX3]=[CX3])][F,Cl,Br,I]"),
    ("alkene", "[CX3]=[CX3]"),
    ("alkyne", "[CX2]#[CX2]"),
    ("aromatic_ring", "c1ccccc1"),
    ("imine", "[CX3]=[NX2]"),
]

# Leaving groups worth recognising when reasoning about substitution/elimination.
LEAVING_GROUP_SMARTS: dict[str, str] = {
    "halide": "[F,Cl,Br,I]",
    "tosylate": "OS(=O)(=O)c1ccc(C)cc1",
    "mesylate": "OS(=O)(=O)C",
    "water": "[OX2H2]",
    "hydroxide_on_C": "[CX4][OX2H1]",
}


_compiled: list[tuple[str, "Chem.Mol"]] | None = None


def _patterns() -> list[tuple[str, "Chem.Mol"]]:
    global _compiled
    if _compiled is None:
        compiled = []
        for name, smarts in FUNCTIONAL_GROUPS:
            q = Chem.MolFromSmarts(smarts)
            if q is not None:
                compiled.append((name, q))
        _compiled = compiled
    return _compiled


def detect_functional_groups(mol: "Chem.Mol") -> list[str]:
    """Return the sorted list of functional-group names present in ``mol``."""
    if mol is None:
        return []
    found = [name for name, q in _patterns() if mol.HasSubstructMatch(q)]
    # de-duplicate while keeping a stable, readable order
    seen: set[str] = set()
    out: list[str] = []
    for name in found:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out
