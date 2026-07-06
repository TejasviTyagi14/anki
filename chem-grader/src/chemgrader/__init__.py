"""chemgrader -- a directed-graph grader for organic reaction mechanisms.

Public surface:

* models          -- MoleculeNode, ReactionEdge, ReactionGraph, ArrowOp, ComparisonOptions
* StructureService -- RDKit canonicalization / identity / properties
* NameResolver / StructureInput -- swappable IUPAC-naming and drawing->SMILES seams
* MechanismRuleLibrary -- SMARTS mechanism templates
* Grader          -- the layered grader producing GradeResult feedback
"""

from __future__ import annotations

from .feedback import EdgeFeedback, GradeResult, NodeFeedback, NodeStatus, ScoreBreakdown
from .grader import Grader, GraderConfig
from .mechanisms import MechanismRuleLibrary, MechanismTemplate
from .models import (
    ArrowOp,
    ComparisonOptions,
    MechanismType,
    MoleculeNode,
    ReactionEdge,
    ReactionGraph,
)
from .name_resolver import MockNameResolver, NameResolver, NullNameResolver
from .structure_input import (
    MockOcrStructureInput,
    MolblockInput,
    SmilesPassthroughInput,
    StructureInput,
)
from .structure_service import MoleculeIdentity, StructureService

__all__ = [
    "ArrowOp",
    "ComparisonOptions",
    "MechanismType",
    "MoleculeNode",
    "ReactionEdge",
    "ReactionGraph",
    "StructureService",
    "MoleculeIdentity",
    "NameResolver",
    "NullNameResolver",
    "MockNameResolver",
    "StructureInput",
    "SmilesPassthroughInput",
    "MolblockInput",
    "MockOcrStructureInput",
    "MechanismRuleLibrary",
    "MechanismTemplate",
    "Grader",
    "GraderConfig",
    "GradeResult",
    "NodeFeedback",
    "EdgeFeedback",
    "NodeStatus",
    "ScoreBreakdown",
]
