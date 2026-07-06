"""Structured, granular feedback returned by the grader.

Deliberately not pass/fail: every node and edge carries its own verdict, the
specific errors/warnings found, and an overall score with a breakdown so a UI can
highlight exactly where a mechanism went wrong.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NodeStatus(str, Enum):
    CORRECT = "correct"  # matches a reference structure
    VALID_ALTERNATIVE = "valid_alternative"  # not in reference but a plausible intermediate
    WRONG = "wrong"  # a structure that shouldn't be here
    MISSING = "missing"  # a reference structure the attempt never drew
    EXTRANEOUS = "extraneous"  # extra structure with no role
    INVALID = "invalid"  # could not be parsed


class NodeFeedback(BaseModel):
    node_id: str
    status: NodeStatus
    smiles: Optional[str] = None
    inchikey: Optional[str] = None
    iupac_name: Optional[str] = None  # display only
    message: str = ""


class EdgeFeedback(BaseModel):
    edge_id: str
    source: str
    target: str
    matches_reference: bool = False

    transformation_plausible: bool = True
    conservation_ok: bool = True

    mechanism_stated: Optional[str] = None
    mechanism_consistent: Optional[bool] = None
    reagents_ok: Optional[bool] = None

    arrows_checked: bool = False
    arrows_ok: bool = True

    changes: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)

    score: float = 0.0  # 0..1 for this edge


class ScoreBreakdown(BaseModel):
    nodes: float = 0.0
    transformations: float = 0.0
    mechanisms: float = 0.0
    pathway: float = 0.0


class GradeResult(BaseModel):
    overall_score: float
    passed: bool
    summary: str
    breakdown: ScoreBreakdown
    nodes: list[NodeFeedback] = Field(default_factory=list)
    edges: list[EdgeFeedback] = Field(default_factory=list)
    hints: list[str] = Field(default_factory=list)
