"""Pluggable structure *input* -> SMILES.

The primary internal format is SMILES. Hand-drawn structures (canvas ink,
photos) or a chemical structure editor (Ketcher) enter the system through this
interface, which converts whatever the frontend produced into SMILES.

This mirrors the ``recognizeHandwriting`` seam in the handwriting prototype: the
recognizer/OCR is a swappable dependency, and the grader downstream only ever
sees clean text (here, SMILES). Provide a real implementation by satisfying
:class:`StructureInput`; the grader/API never need to change.

Contract: ``to_smiles`` returns a SMILES string or raises :class:`StructureInputError`.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from rdkit import Chem


class StructureInputError(ValueError):
    """Raised when an input payload cannot be turned into a structure."""


@runtime_checkable
class StructureInput(Protocol):
    """Convert an arbitrary drawing/editor payload into SMILES."""

    def to_smiles(self, payload: Any) -> str:  # pragma: no cover - protocol
        ...


class SmilesPassthroughInput:
    """Trivial input source: the payload already contains SMILES.

    Accepts either a raw SMILES string or a dict ``{"smiles": "..."}``. Validates
    the SMILES via RDKit so bad input fails fast at the boundary.
    """

    def to_smiles(self, payload: Any) -> str:
        smiles = payload.get("smiles") if isinstance(payload, dict) else payload
        if not isinstance(smiles, str) or not smiles.strip():
            raise StructureInputError("expected a non-empty SMILES string")
        if Chem.MolFromSmiles(smiles) is None:
            raise StructureInputError(f"payload SMILES did not parse: {smiles!r}")
        return Chem.MolToSmiles(Chem.MolFromSmiles(smiles))


class MolblockInput:
    """Convert an MDL molblock (what Ketcher exports) into SMILES.

    Accepts a raw molblock string or ``{"molblock": "..."}``. This is the natural
    plug-in point for a Ketcher editor on the frontend.
    """

    def to_smiles(self, payload: Any) -> str:
        molblock = payload.get("molblock") if isinstance(payload, dict) else payload
        if not isinstance(molblock, str) or not molblock.strip():
            raise StructureInputError("expected a non-empty molblock")
        mol = Chem.MolFromMolBlock(molblock)
        if mol is None:
            raise StructureInputError("molblock did not parse")
        return Chem.MolToSmiles(mol)


class MockOcrStructureInput:
    """A stand-in for a hand-drawing / OCR-to-SMILES model.

    Looks up a caption/label in a small fixture table. Real deployments replace
    this with an image->SMILES model; the fixture keeps the pipeline testable
    end-to-end without one. Accepts ``{"label": "..."}`` or ``{"image": <ignored>,
    "label": "..."}``.
    """

    _FIXTURES: dict[str, str] = {
        "tert-butyl bromide": "CC(C)(C)Br",
        "tert-butanol": "CC(C)(C)O",
        "ethanol": "CCO",
        "bromoethane": "CCBr",
        "propene": "CC=C",
        "acetone": "CC(C)=O",
        "benzene": "c1ccccc1",
    }

    def to_smiles(self, payload: Any) -> str:
        label = payload.get("label") if isinstance(payload, dict) else payload
        if not isinstance(label, str):
            raise StructureInputError("mock OCR expects a 'label' to look up")
        key = label.strip().lower()
        for name, smiles in self._FIXTURES.items():
            if name.lower() == key:
                return smiles
        raise StructureInputError(f"mock OCR has no fixture for {label!r}")
