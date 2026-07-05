"""MechGrader AI rubric grader (Stage 2).

An HONEST, provider-agnostic LLM adapter that assigns partial credit on mechanism
QUALITY (arrow-pushing, intermediate reasonableness, step ordering) ON TOP OF and
CONSTRAINED BY the deterministic RDKit grade (:mod:`mechgrader.grading`).

Design in one breath: the deterministic grade is passed IN (so this package needs
neither RDKit nor Anki); credentials are read from the environment ONLY; a global
kill switch runs everything AI-OFF with no network when there is no provider/key;
the RDKit-validated mechanism is sent to the model as sanitised DATA (never
instructions); every judgment must cite a rubric line + reference step or it earns
no credit; the model can never override a deterministic verdict; and broken JSON /
offline / rate-limit degrade gracefully back to the deterministic grade.

Public API::

    from mechgrader.ai import grade
    combined = grade(submission, reference, deterministic_grade=det)

See :func:`mechgrader.ai.grader_llm.grade` for the combined-grade schema.
"""

from __future__ import annotations

from .config import (
    AiConfig,
    is_truthy,
    load_config,
    provider_family,
)
from .grader_llm import grade
from .prompt import SYSTEM_PROMPT, neutralize_text
from .rubric import CRITERIA, RUBRIC, RUBRIC_ID, RUBRIC_VERSION, line_ids
from .transport import LlmClient, LlmError, TransportError, UrllibTransport

__all__ = [
    "grade",
    "AiConfig",
    "load_config",
    "is_truthy",
    "provider_family",
    "RUBRIC",
    "RUBRIC_ID",
    "RUBRIC_VERSION",
    "CRITERIA",
    "line_ids",
    "neutralize_text",
    "SYSTEM_PROMPT",
    "LlmClient",
    "UrllibTransport",
    "TransportError",
    "LlmError",
]
