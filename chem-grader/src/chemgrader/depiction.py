"""RDKit 2D depiction with optional atom/bond highlighting.

Self-hosted, index-accurate structure rendering so the UI can point at the exact
bond/atom that differs (the frontend uses the same canonical SMILES, so RDKit's
atom numbering here matches the indices returned by :func:`structural_diff`).

This is a display utility — it does not touch grading logic.
"""

from __future__ import annotations

from typing import Optional

from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D

from .structure_service import StructureError

# soft red = "this is the problem/difference"
_DEFAULT_COLOR = (0.98, 0.60, 0.60)


def render_svg(
    smiles: str,
    highlight_atoms: Optional[list[int]] = None,
    highlight_bonds: Optional[list[list[int]]] = None,  # list of [a, b] atom-index pairs
    width: int = 280,
    height: int = 200,
    color: tuple[float, float, float] = _DEFAULT_COLOR,
) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise StructureError(f"invalid SMILES: {smiles!r}")
    rdDepictor.Compute2DCoords(mol)

    n = mol.GetNumAtoms()
    atoms = [int(i) for i in (highlight_atoms or []) if 0 <= int(i) < n]

    bond_ids: list[int] = []
    for pair in highlight_bonds or []:
        if len(pair) == 2:
            b = mol.GetBondBetweenAtoms(int(pair[0]), int(pair[1]))
            if b is not None:
                bond_ids.append(b.GetIdx())

    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    opts = drawer.drawOptions()
    opts.clearBackground = False
    drawer.DrawMolecule(
        mol,
        highlightAtoms=atoms,
        highlightBonds=bond_ids,
        highlightAtomColors={i: color for i in atoms},
        highlightBondColors={i: color for i in bond_ids},
    )
    drawer.FinishDrawing()
    return drawer.GetDrawingText()
