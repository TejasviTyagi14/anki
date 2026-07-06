"""Core data models for the reaction-mechanism grader.

A mechanism is a *directed graph*:

* :class:`MoleculeNode` — a molecular structure, identified canonically.
* :class:`ReactionEdge`  — a reaction step (reagents, conditions, mechanism
  type, optional arrow-pushing) from one structure to another.
* :class:`ReactionGraph` — the whole submission; supports branching and
  convergent pathways, not just linear chains.

Design rule (important): a node's *identity* is its canonical SMILES / InChIKey,
computed by :mod:`chemgrader.structure_service`. IUPAC names are stored only as a
human-readable ``iupac_name`` label and are **never** used for grading identity.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

import networkx as nx
from pydantic import BaseModel, Field, model_validator


class MechanismType(str, Enum):
    """Common MCAT-relevant mechanism categories.

    ``mechanism_type`` on an edge is a free string (so callers can pass anything),
    but these are the canonical spellings the rule library understands. Use
    :func:`normalize_mechanism_type` to map loose input onto these.
    """

    SN1 = "SN1"
    SN2 = "SN2"
    E1 = "E1"
    E2 = "E2"
    ELECTROPHILIC_ADDITION = "electrophilic_addition"
    NUCLEOPHILIC_ADDITION = "nucleophilic_addition"
    NUCLEOPHILIC_ACYL_SUBSTITUTION = "nucleophilic_acyl_substitution"
    ELECTROPHILIC_AROMATIC_SUBSTITUTION = "electrophilic_aromatic_substitution"
    OXIDATION = "oxidation"
    REDUCTION = "reduction"
    ACID_BASE = "acid_base"
    UNKNOWN = "unknown"


_ALIASES = {
    "sn1": MechanismType.SN1,
    "sn2": MechanismType.SN2,
    "e1": MechanismType.E1,
    "e2": MechanismType.E2,
    "electrophilic addition": MechanismType.ELECTROPHILIC_ADDITION,
    "markovnikov addition": MechanismType.ELECTROPHILIC_ADDITION,
    "nucleophilic addition": MechanismType.NUCLEOPHILIC_ADDITION,
    "nucleophilic acyl substitution": MechanismType.NUCLEOPHILIC_ACYL_SUBSTITUTION,
    "acyl substitution": MechanismType.NUCLEOPHILIC_ACYL_SUBSTITUTION,
    "eas": MechanismType.ELECTROPHILIC_AROMATIC_SUBSTITUTION,
    "electrophilic aromatic substitution": MechanismType.ELECTROPHILIC_AROMATIC_SUBSTITUTION,
    "oxidation": MechanismType.OXIDATION,
    "reduction": MechanismType.REDUCTION,
    "acid-base": MechanismType.ACID_BASE,
    "acid base": MechanismType.ACID_BASE,
    "proton transfer": MechanismType.ACID_BASE,
}


def normalize_mechanism_type(value: Optional[str]) -> MechanismType:
    """Map loose user input (``"Sn2"``, ``"E 2"``, ...) onto a MechanismType."""
    if value is None:
        return MechanismType.UNKNOWN
    key = " ".join(value.strip().lower().replace("_", " ").split())
    if key in _ALIASES:
        return _ALIASES[key]
    compact = key.replace(" ", "")
    for member in MechanismType:
        if member.value.lower() == compact or member.name.lower() == compact:
            return member
    return MechanismType.UNKNOWN


class ArrowOp(BaseModel):
    """A single curved-arrow (electron-flow) operation.

    Endpoints are strings so one model covers atoms, bonds and lone pairs. Atom
    indices are 0-based indices into the *source* (reactant) molecule:

    * ``"atom:3"``   — atom 3
    * ``"bond:3-4"`` — the bond between atoms 3 and 4
    * ``"lp:3"``     — a lone pair on atom 3
    """

    source: str
    target: str
    electrons: int = 2  # 2 = curved arrow (electron pair); 1 = fishhook (radical)
    label: Optional[str] = None


class MoleculeNode(BaseModel):
    """A molecular structure in the mechanism graph.

    Only ``id`` and ``smiles`` are required on input. The identity/property
    fields are filled in by :meth:`chemgrader.structure_service.StructureService.enrich`.
    """

    id: str
    smiles: str
    label: Optional[str] = None

    # --- derived identity + properties (populated during enrichment) ---
    canonical_smiles: Optional[str] = None
    inchi: Optional[str] = None
    inchikey: Optional[str] = None
    formula: Optional[str] = None
    mol_weight: Optional[float] = None
    functional_groups: list[str] = Field(default_factory=list)
    # Display-only; produced by a NameResolver. NEVER used for grading identity.
    iupac_name: Optional[str] = None
    # Set if the SMILES could not be parsed. Grading degrades gracefully.
    error: Optional[str] = None


class ReactionEdge(BaseModel):
    """A reaction step from ``source`` structure to ``target`` structure."""

    id: str
    source: str
    target: str
    reagents: list[str] = Field(default_factory=list)
    solvent: Optional[str] = None
    conditions: Optional[str] = None
    mechanism_type: Optional[str] = None
    arrows: list[ArrowOp] = Field(default_factory=list)
    notes: Optional[str] = None


class ReactionGraph(BaseModel):
    """A directed graph of structures and the steps between them."""

    id: Optional[str] = None
    title: Optional[str] = None
    nodes: list[MoleculeNode]
    edges: list[ReactionEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_references(self) -> "ReactionGraph":
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate node ids in graph")
        idset = set(ids)
        edge_ids = [e.id for e in self.edges]
        if len(set(edge_ids)) != len(edge_ids):
            raise ValueError("duplicate edge ids in graph")
        for e in self.edges:
            if e.source not in idset:
                raise ValueError(f"edge {e.id} references unknown source node {e.source!r}")
            if e.target not in idset:
                raise ValueError(f"edge {e.id} references unknown target node {e.target!r}")
        return self

    # ------------------------------------------------------------------ #
    # convenience accessors
    # ------------------------------------------------------------------ #
    def node(self, node_id: str) -> MoleculeNode:
        for n in self.nodes:
            if n.id == node_id:
                return n
        raise KeyError(node_id)

    def node_map(self) -> dict[str, MoleculeNode]:
        return {n.id: n for n in self.nodes}

    def to_networkx(self) -> nx.DiGraph:
        """Build a NetworkX DiGraph (used by the alignment/grading logic)."""
        g = nx.DiGraph()
        for n in self.nodes:
            g.add_node(n.id, molecule=n)
        for e in self.edges:
            g.add_edge(e.source, e.target, edge=e)
        return g

    def start_nodes(self) -> list[str]:
        """Nodes with no incoming edge (reaction starting materials)."""
        targets = {e.target for e in self.edges}
        return [n.id for n in self.nodes if n.id not in targets]

    def end_nodes(self) -> list[str]:
        """Nodes with no outgoing edge (final products)."""
        sources = {e.source for e in self.edges}
        return [n.id for n in self.nodes if n.id not in sources]


class ComparisonOptions(BaseModel):
    """Toggleable tolerances for node identity comparison.

    These mirror the "matching modes" idea from the handwriting prototype
    (lenient / normalized / exact) but for chemical structures.
    """

    ignore_stereo: bool = False
    allow_tautomers: bool = False
    # Neutralize formal charges before comparison. A coarse stand-in for
    # resonance / protonation-state tolerance -- see StructureService.same_molecule.
    ignore_charge: bool = False
