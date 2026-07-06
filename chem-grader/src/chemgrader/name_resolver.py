"""Pluggable structure -> IUPAC name resolution (display only).

IUPAC naming is **not** used for grading identity -- it is error-prone and not
reliably round-trippable. It exists purely as a human-readable label. This module
defines a small interface plus mock implementations so you can later drop in an
external model/service (e.g. STOUT, an online naming API, a commercial toolkit)
*without touching the grader*.

Contract: ``to_iupac`` returns a best-effort name or ``None``. It must never
raise -- callers treat naming as optional and grading never depends on it.
"""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from rdkit import Chem
from rdkit.Chem import rdMolDescriptors


@runtime_checkable
class NameResolver(Protocol):
    """Turn a structure (canonical SMILES) into a display IUPAC name."""

    def to_iupac(self, smiles: str) -> Optional[str]:  # pragma: no cover - protocol
        ...


class NullNameResolver:
    """Always returns ``None`` -- the safe default when no namer is configured."""

    def to_iupac(self, smiles: str) -> Optional[str]:
        return None


class MockNameResolver:
    """A deterministic stand-in for a real structure->IUPAC model.

    Uses a tiny built-in lookup for common MCAT molecules and otherwise returns a
    clearly-marked placeholder derived from the molecular formula. This lets the
    rest of the system exercise the "display name" path in tests without a network
    call or a heavyweight model.

    Swap this out by implementing :class:`NameResolver` and passing your instance
    to :class:`chemgrader.grader.Grader` / ``StructureService.enrich``.
    """

    _KNOWN: dict[str, str] = {
        "CCO": "ethanol",
        "CO": "methanol",
        "CC(=O)O": "acetic acid",
        "CC=O": "acetaldehyde",
        "CC(C)=O": "propan-2-one",
        "C=C": "ethene",
        "CCBr": "bromoethane",
        "CCCl": "chloroethane",
        "c1ccccc1": "benzene",
        "CC(C)(C)Br": "2-bromo-2-methylpropane",
        "CC(C)(C)O": "2-methylpropan-2-ol",
        "CC(C)(C)[OH]": "2-methylpropan-2-ol",
        "CC(=O)Cl": "acetyl chloride",
        "CC(N)=O": "acetamide",
    }

    def to_iupac(self, smiles: str) -> Optional[str]:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        canonical = Chem.MolToSmiles(mol)
        if canonical in self._KNOWN:
            return self._KNOWN[canonical]
        formula = rdMolDescriptors.CalcMolFormula(mol)
        # Clearly-marked placeholder so nobody mistakes it for a real name.
        return f"[unnamed {formula}]"
