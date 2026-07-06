"""RDKit-backed structure handling: canonicalization, identity and properties.

This is the single source of truth for *what a molecule is*. Everything the
grader compares (node identity, transformation endpoints) flows through here so
the notion of "same molecule" is defined in exactly one place.

Identity = canonical SMILES / InChIKey. IUPAC names are display-only and are
produced elsewhere (see :mod:`chemgrader.name_resolver`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, rdMolDescriptors

from .functional_groups import detect_functional_groups
from .models import ComparisonOptions, MoleculeNode

# RDKit is chatty on stderr (e.g. "Omitted undefined stereo"). Silence info/warn
# but keep errors -- we detect real parse failures via None returns anyway.
RDLogger.DisableLog("rdApp.info")
RDLogger.DisableLog("rdApp.warning")

# Tautomer/charge normalisation helpers are optional across RDKit builds.
try:  # pragma: no cover - availability depends on the RDKit build
    from rdkit.Chem.MolStandardize import rdMolStandardize

    _HAVE_STANDARDIZE = True
except Exception:  # pragma: no cover
    _HAVE_STANDARDIZE = False


class StructureError(ValueError):
    """Raised when a SMILES / molfile cannot be parsed into a molecule."""


@dataclass
class MoleculeIdentity:
    """The canonical identity + basic properties of a structure."""

    canonical_smiles: str
    inchi: str
    inchikey: str
    formula: str
    mol_weight: float
    functional_groups: list[str] = field(default_factory=list)


class StructureService:
    """Parse, canonicalize, identify and compare molecular structures."""

    # ------------------------------------------------------------------ #
    # parsing
    # ------------------------------------------------------------------ #
    def parse(self, smiles: str) -> Chem.Mol:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            raise StructureError(f"could not parse SMILES: {smiles!r}")
        return mol

    def try_parse(self, smiles: str) -> Optional[Chem.Mol]:
        return Chem.MolFromSmiles(smiles)

    def mol_from_molblock(self, molblock: str) -> Chem.Mol:
        """Parse an MDL molfile/molblock (e.g. what Ketcher emits)."""
        mol = Chem.MolFromMolBlock(molblock)
        if mol is None:
            raise StructureError("could not parse molblock")
        return mol

    def molblock_to_smiles(self, molblock: str) -> str:
        return Chem.MolToSmiles(self.mol_from_molblock(molblock))

    # ------------------------------------------------------------------ #
    # canonical identity + properties
    # ------------------------------------------------------------------ #
    def canonical_smiles(self, smiles: str) -> str:
        return Chem.MolToSmiles(self.parse(smiles))

    def inchi(self, mol_or_smiles) -> str:
        mol = self._as_mol(mol_or_smiles)
        return Chem.MolToInchi(mol)

    def inchikey(self, mol_or_smiles) -> str:
        return Chem.InchiToInchiKey(self.inchi(mol_or_smiles))

    def formula(self, mol_or_smiles) -> str:
        return rdMolDescriptors.CalcMolFormula(self._as_mol(mol_or_smiles))

    def mol_weight(self, mol_or_smiles) -> float:
        return round(Descriptors.MolWt(self._as_mol(mol_or_smiles)), 4)

    def identity(self, smiles: str) -> MoleculeIdentity:
        mol = self.parse(smiles)
        inchi = Chem.MolToInchi(mol)
        return MoleculeIdentity(
            canonical_smiles=Chem.MolToSmiles(mol),
            inchi=inchi,
            inchikey=Chem.InchiToInchiKey(inchi),
            formula=rdMolDescriptors.CalcMolFormula(mol),
            mol_weight=round(Descriptors.MolWt(mol), 4),
            functional_groups=detect_functional_groups(mol),
        )

    def enrich(self, node: MoleculeNode, name_resolver=None) -> MoleculeNode:
        """Populate a node's identity/property fields in place and return it.

        Never raises: a bad SMILES sets ``node.error`` and leaves identity blank
        so grading can degrade gracefully instead of crashing.
        """
        mol = self.try_parse(node.smiles)
        if mol is None:
            node.error = f"invalid SMILES: {node.smiles!r}"
            return node
        try:
            ident = self.identity(node.smiles)
            node.canonical_smiles = ident.canonical_smiles
            node.inchi = ident.inchi
            node.inchikey = ident.inchikey
            node.formula = ident.formula
            node.mol_weight = ident.mol_weight
            node.functional_groups = ident.functional_groups
            node.error = None
        except Exception as exc:  # pragma: no cover - defensive
            node.error = f"could not compute identity: {exc}"
            return node

        # IUPAC name is display-only and must never block grading.
        if name_resolver is not None:
            try:
                node.iupac_name = name_resolver.to_iupac(node.canonical_smiles)
            except Exception:
                node.iupac_name = None
        return node

    # ------------------------------------------------------------------ #
    # comparison (the tolerance flags live here)
    # ------------------------------------------------------------------ #
    def comparison_key(self, smiles: str, options: Optional[ComparisonOptions] = None) -> str:
        """A string key such that two structures are "the same" (under the given
        tolerances) iff their keys are equal. Used to bucket graph nodes."""
        options = options or ComparisonOptions()
        mol = self.parse(smiles)
        mol = self._normalize_for_comparison(mol, options)
        try:
            return Chem.InchiToInchiKey(Chem.MolToInchi(mol))
        except Exception:
            # Fall back to canonical SMILES if InChI generation fails.
            return "SMILES:" + Chem.MolToSmiles(mol)

    def same_molecule(
        self,
        smiles_a: str,
        smiles_b: str,
        options: Optional[ComparisonOptions] = None,
    ) -> bool:
        try:
            return self.comparison_key(smiles_a, options) == self.comparison_key(
                smiles_b, options
            )
        except StructureError:
            return False

    def _normalize_for_comparison(
        self, mol: Chem.Mol, options: ComparisonOptions
    ) -> Chem.Mol:
        mol = Chem.Mol(mol)  # work on a copy
        if options.ignore_charge and _HAVE_STANDARDIZE:
            try:
                mol = rdMolStandardize.Uncharger().uncharge(mol)
            except Exception:
                pass
        if options.allow_tautomers and _HAVE_STANDARDIZE:
            try:
                mol = rdMolStandardize.TautomerEnumerator().Canonicalize(mol)
            except Exception:
                pass
        if options.ignore_stereo:
            Chem.RemoveStereochemistry(mol)
        return mol

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _as_mol(self, mol_or_smiles) -> Chem.Mol:
        if isinstance(mol_or_smiles, Chem.Mol):
            return mol_or_smiles
        return self.parse(mol_or_smiles)


def count_unsaturation(mol: Chem.Mol) -> int:
    """Rings + pi bonds (double counts once, triple twice).

    A cheap proxy for degrees of unsaturation used to sanity-check whether a
    transformation added/removed unsaturation (e.g. elimination, addition).
    """
    work = Chem.Mol(mol)
    try:
        Chem.Kekulize(work, clearAromaticFlags=True)
    except Exception:
        pass
    pi = 0
    for bond in work.GetBonds():
        order = bond.GetBondTypeAsDouble()
        if order >= 2:
            pi += int(round(order)) - 1
    return rdMolDescriptors.CalcNumRings(work) + pi
