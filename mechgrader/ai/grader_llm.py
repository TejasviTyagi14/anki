"""AI rubric grader adapter -- quality partial-credit ON TOP OF, and CONSTRAINED
BY, the deterministic grade.

Public entry point: :func:`grade`. It takes the deterministic grade dict as an
INPUT (dependency injection) so this module needs neither RDKit nor Anki, and
returns a COMBINED grade: every deterministic field, plus an ``ai`` sub-dict.

Guarantees (project spec / ``docs/ai_eval.md`` / ``docs/robustness.md`` rows 4 & 10):

* **AI-OFF by default.** With no provider/key -- or the kill switch set -- it
  returns the deterministic grade untouched, ``ai_status == "off"``, and makes
  NO network call (an injected client is not even consulted).
* **Constrained.** The LLM cannot override deterministic verdicts: if
  ``product_match`` is false the AI ``overall`` is clamped away from "correct".
  The deterministic ``score`` / ``passed`` are never changed by AI.
* **Cited or dropped.** Every per-criterion judgment must cite a rubric line id
  and a reference step; uncited judgments are zeroed (no citation, no credit).
* **Robust.** Broken/invalid LLM JSON is retried (bounded); on repeated failure,
  offline, or rate-limit it falls back to the deterministic grade. It never
  raises into the review.

Combined-grade schema (returned dict)::

    {
      # --- all deterministic fields, verbatim (authoritative) --------------
      "valid": bool, "score": int, "product_match": bool, "balance_ok": bool,
      "per_step": [...], "reasons": [str], "passed": bool, ...,
      # --- AI sub-dict (added by this module) -----------------------------
      "ai": {
        "ai_used": bool,
        "ai_status": "ok" | "off" | "fallback",
        "provider": str | None,
        "model": str | None,
        "rubric_id": str, "rubric_version": int,
        "overall": "correct" | "partial" | "incorrect",
        "per_criterion": {
           "arrow_pushing": {"score": int, "source_refs": [ref], "comment": str, "rejected": bool},
           "intermediate_reasonableness": {...},
           "step_ordering": {...},
        },
        "source_refs": [ {"rubric_line": str, "reference_step": int}, ... ],
        "clamped": bool,
        "reasons": [str],
      },
    }

where each ``ref`` is ``{"rubric_line": <rubric line id>, "reference_step": <int>}``.
"""

from __future__ import annotations

import copy
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from . import prompt as _prompt
from . import rubric as _rubric
from .config import AiConfig, load_config
from .transport import LlmClient, LlmError, TransportError

__all__ = ["grade", "AiConfig", "load_config"]

# Overall grade ordering, used for clamping (higher = more credit).
_OVERALL_RANK = {"incorrect": 0, "partial": 1, "correct": 2}
_RANK_OVERALL = {rank: name for name, rank in _OVERALL_RANK.items()}

# Synonyms the model might emit for the overall grade.
_OVERALL_SYNONYMS = {
    "correct": "correct",
    "pass": "correct",
    "passing": "correct",
    "full": "correct",
    "full_credit": "correct",
    "partial": "partial",
    "partially_correct": "partial",
    "partial_credit": "partial",
    "incorrect": "incorrect",
    "wrong": "incorrect",
    "fail": "incorrect",
    "failing": "incorrect",
    "no_credit": "incorrect",
    "none": "incorrect",
}


class _JsonError(ValueError):
    """The LLM response was not parseable JSON (triggers a bounded retry)."""


class _SchemaError(ValueError):
    """The LLM JSON was missing required structure (triggers a bounded retry)."""


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def grade(
    submission: dict,
    reference: dict,
    *,
    deterministic_grade: dict,
    rubric: Optional[dict] = None,
    client: Any = None,
    config: Optional[AiConfig] = None,
    env: Optional[Dict[str, str]] = None,
) -> dict:
    """Grade mechanism QUALITY on top of a deterministic grade; return combined.

    Parameters
    ----------
    submission, reference : the structured mechanisms (dicts). Only forwarded to
        the LLM as sanitised DATA; never parsed here (no RDKit needed).
    deterministic_grade : the authoritative grade dict from
        ``mechgrader.grading.deterministic`` (dependency-injected). Its fields
        pass through unchanged and constrain the AI.
    rubric : optional rubric override; defaults to :data:`mechgrader.ai.rubric.RUBRIC`.
    client : optional LLM client exposing ``complete(system, user) -> str``.
        Injected by tests (a fake) so no network is used. When AI is OFF the
        client is NOT consulted at all.
    config / env : optional configuration injection. ``config`` wins; else
        ``load_config(env)``; else ``load_config(os.environ)``.
    """
    if not isinstance(deterministic_grade, dict):
        raise TypeError("deterministic_grade must be a dict (dependency-injected)")

    rubric = rubric or _rubric.RUBRIC
    combined = copy.deepcopy(deterministic_grade)  # never mutate the caller's dict
    cfg = config if config is not None else load_config(env if env is not None else os.environ)

    # 1. Global kill switch -> AI-OFF. No client use, no network.
    if not cfg.enabled:
        return _attach(combined, _off_ai(deterministic_grade, cfg, rubric))

    # 2. Injection precondition: never send an un-validated mechanism to the LLM.
    if not deterministic_grade.get("valid"):
        return _attach(
            combined,
            _fallback_ai(
                deterministic_grade,
                cfg,
                rubric,
                reason="deterministic result is not RDKit-valid; AI grading skipped",
            ),
        )

    product_match = bool(deterministic_grade.get("product_match"))
    n_steps = _reference_step_count(reference)

    # 3. Build the hardened DATA payload + prompt (all inputs treated as data).
    payload = _prompt.build_payload(submission, reference, deterministic_grade, rubric)
    user = _prompt.build_user_message(payload)
    system = _prompt.SYSTEM_PROMPT

    # 4. A real client is constructed only when enabled and none was injected.
    if client is None:
        try:
            client = LlmClient(cfg)
        except Exception as exc:  # pragma: no cover - defensive; ctor is trivial
            return _attach(
                combined,
                _fallback_ai(
                    deterministic_grade,
                    cfg,
                    rubric,
                    reason=f"could not initialise LLM client: {exc}",
                ),
            )

    # 5. Bounded retry on broken/invalid JSON; graceful fallback otherwise.
    max_attempts = 1 + max(0, int(cfg.max_retries))
    last_reason = "no attempt was made"
    for attempt in range(1, max_attempts + 1):
        try:
            text = client.complete(system, user)
        except TransportError as exc:
            # Offline / rate-limit / HTTP error: don't hammer -- fall back now.
            last_reason = f"provider unavailable (offline/rate-limit): {exc}"
            break
        except Exception as exc:  # any client failure -> fall back, never crash
            last_reason = f"LLM call failed: {exc}"
            break

        try:
            raw = _extract_json(text)
            per_criterion, overall, refs = _parse_judgment(raw, rubric, n_steps)
        except (_JsonError, _SchemaError) as exc:
            last_reason = f"invalid LLM JSON (attempt {attempt}/{max_attempts}): {exc}"
            continue  # retry

        return _attach(
            combined,
            _ok_ai(
                deterministic_grade,
                cfg,
                rubric,
                per_criterion,
                overall,
                refs,
                product_match,
                attempt,
            ),
        )

    return _attach(
        combined,
        _fallback_ai(
            deterministic_grade, cfg, rubric, reason=last_reason, attempts=max_attempts
        ),
    )


# --------------------------------------------------------------------------- #
# LLM output parsing + citation enforcement
# --------------------------------------------------------------------------- #
def _extract_json(text: str) -> Dict[str, Any]:
    """Parse a JSON object out of ``text`` (tolerating leading/trailing prose)."""
    text = (text or "").strip()
    if not text:
        raise _JsonError("empty LLM response")
    try:
        obj = json.loads(text)
    except (ValueError, TypeError):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = json.loads(text[start : end + 1])
            except (ValueError, TypeError) as exc:
                raise _JsonError("LLM response was not valid JSON") from exc
        else:
            raise _JsonError("LLM response was not valid JSON")
    if not isinstance(obj, dict):
        raise _JsonError("LLM response JSON was not an object")
    return obj


def _normalize_overall(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    return _OVERALL_SYNONYMS.get(value.strip().lower().replace(" ", "_").replace("-", "_"))


def _coerce_score(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, score))


def _resolve_source_ref(
    ref: Any, n_steps: int, valid_line_ids: set
) -> Optional[Dict[str, Any]]:
    """Return a normalised source_ref if it cites a real rubric line (+ in-range
    reference step), else ``None``. Lenient on key names, strict on validity."""
    if not isinstance(ref, dict):
        return None

    line = ref.get("rubric_line", ref.get("line", ref.get("rubric")))
    if not isinstance(line, str) or line.strip() not in valid_line_ids:
        return None
    line = line.strip()

    step = ref.get("reference_step", ref.get("step", ref.get("ref_step")))
    if isinstance(step, bool):
        return None

    if n_steps > 0:
        # A concrete reference exists: the cited step MUST be in range.
        if not isinstance(step, int) or not (0 <= step < n_steps):
            return None
        return {"rubric_line": line, "reference_step": step}

    # No reference steps to cite against: a valid rubric line alone suffices.
    resolved: Dict[str, Any] = {"rubric_line": line}
    if isinstance(step, int):
        resolved["reference_step"] = step
    return resolved


def _parse_criterion(
    entry: Any, n_steps: int, valid_line_ids: set
) -> Tuple[int, List[Dict[str, Any]], str, bool]:
    """Parse one criterion into ``(score, valid_refs, comment, rejected)``.

    A criterion with no VALID source_ref is rejected: zeroed, refs dropped. No
    citation, no credit.
    """
    if not isinstance(entry, dict):
        return 0, [], "", True

    raw_refs = entry.get("source_refs")
    if raw_refs is None and "source_ref" in entry:
        raw_refs = [entry["source_ref"]]

    refs: List[Dict[str, Any]] = []
    if isinstance(raw_refs, list):
        for candidate in raw_refs:
            resolved = _resolve_source_ref(candidate, n_steps, valid_line_ids)
            if resolved is not None:
                refs.append(resolved)

    comment = entry.get("comment")
    comment = _prompt.neutralize_text(comment) if isinstance(comment, str) else ""

    if not refs:
        return 0, [], comment, True  # rejected: no valid citation
    return _coerce_score(entry.get("score")), refs, comment, False


def _parse_judgment(
    raw: Dict[str, Any], rubric: Dict[str, Any], n_steps: int
) -> Tuple[Dict[str, Any], str, List[Dict[str, Any]]]:
    """Validate + resolve an LLM judgment into per-criterion output + overall.

    Raises :class:`_SchemaError` when required top-level structure is missing so
    the caller retries. Individual malformed criteria are coerced to
    zeroed/rejected rather than failing the whole parse (robustness).
    """
    per = raw.get("per_criterion")
    if not isinstance(per, dict):
        raise _SchemaError("missing 'per_criterion' object")

    overall = _normalize_overall(raw.get("overall"))
    if overall is None:
        raise _SchemaError("missing or unrecognised 'overall' grade")

    valid_line_ids = _rubric.line_ids(rubric)
    per_out: Dict[str, Any] = {}
    all_refs: List[Dict[str, Any]] = []
    for criterion in _rubric.CRITERIA:
        score, refs, comment, rejected = _parse_criterion(
            per.get(criterion), n_steps, valid_line_ids
        )
        per_out[criterion] = {
            "score": score,
            "source_refs": refs,
            "comment": comment,
            "rejected": rejected,
        }
        all_refs.extend(refs)

    return per_out, overall, _dedupe_refs(all_refs)


def _dedupe_refs(refs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: List[Tuple[Any, Any]] = []
    out: List[Dict[str, Any]] = []
    for ref in refs:
        key = (ref.get("rubric_line"), ref.get("reference_step"))
        if key not in seen:
            seen.append(key)
            out.append(ref)
    return out


# --------------------------------------------------------------------------- #
# result assembly (off / ok / fallback)
# --------------------------------------------------------------------------- #
def _reference_step_count(reference: Any) -> int:
    if isinstance(reference, dict) and isinstance(reference.get("steps"), list):
        return len(reference["steps"])
    return 0


def _deterministic_overall(det: Dict[str, Any]) -> str:
    """Overall grade implied by the deterministic verdict alone (honest, derived)."""
    if det.get("passed"):
        return "correct"
    if det.get("valid") and (_coerce_score(det.get("score")) > 0 or det.get("product_match")):
        return "partial"
    return "incorrect"


def _ceiling(det: Dict[str, Any]) -> str:
    """The highest overall the AI may assign given the deterministic verdict."""
    return "correct" if det.get("product_match") else "partial"


def _attach(combined: Dict[str, Any], ai: Dict[str, Any]) -> Dict[str, Any]:
    combined["ai"] = ai
    return combined


def _ai_shell(
    *,
    status: str,
    used: bool,
    overall: str,
    per_criterion: Dict[str, Any],
    source_refs: List[Dict[str, Any]],
    reasons: List[str],
    clamped: bool,
    rubric: Dict[str, Any],
    provider: Optional[str],
    model: Optional[str],
) -> Dict[str, Any]:
    return {
        "ai_used": used,
        "ai_status": status,
        "provider": provider or None,
        "model": model or None,
        "rubric_id": rubric.get("id"),
        "rubric_version": rubric.get("version"),
        "overall": overall,
        "per_criterion": per_criterion,
        "source_refs": source_refs,
        "clamped": clamped,
        "reasons": reasons,
    }


def _off_ai(det: Dict[str, Any], cfg: AiConfig, rubric: Dict[str, Any]) -> Dict[str, Any]:
    return _ai_shell(
        status="off",
        used=False,
        overall=_deterministic_overall(det),
        per_criterion={},
        source_refs=[],
        reasons=[
            cfg.off_reason or "AI disabled",
            "showing deterministic-only grade (no network call made)",
        ],
        clamped=False,
        rubric=rubric,
        provider=None,  # nothing was selected/used
        model=None,
    )


def _fallback_ai(
    det: Dict[str, Any],
    cfg: AiConfig,
    rubric: Dict[str, Any],
    *,
    reason: str,
    attempts: Optional[int] = None,
) -> Dict[str, Any]:
    reasons = ["AI unavailable - fell back to the deterministic grade.", reason]
    if attempts:
        reasons.append(f"tried {attempts} time(s) before falling back.")
    return _ai_shell(
        status="fallback",
        used=False,
        overall=_deterministic_overall(det),
        per_criterion={},
        source_refs=[],
        reasons=reasons,
        clamped=False,
        rubric=rubric,
        provider=cfg.provider,
        model=cfg.model,
    )


def _ok_ai(
    det: Dict[str, Any],
    cfg: AiConfig,
    rubric: Dict[str, Any],
    per_criterion: Dict[str, Any],
    overall: str,
    refs: List[Dict[str, Any]],
    product_match: bool,
    attempt: int,
) -> Dict[str, Any]:
    ceiling = _ceiling(det)
    clamped = _OVERALL_RANK[overall] > _OVERALL_RANK[ceiling]
    final_overall = _RANK_OVERALL[min(_OVERALL_RANK[overall], _OVERALL_RANK[ceiling])]

    reasons = [f"AI rubric grade via {cfg.family} provider (attempt {attempt})."]
    if clamped:
        reasons.append(
            f"'overall' clamped from '{overall}' to '{final_overall}': deterministic "
            f"product_match is {product_match}, so the mechanism cannot be graded "
            "correct/passing."
        )
    rejected = sorted(cid for cid, entry in per_criterion.items() if entry.get("rejected"))
    if rejected:
        reasons.append("no citation, no credit - zeroed uncited criteria: " + ", ".join(rejected))
    reasons.append(
        "AI adds quality partial-credit only; deterministic score/passed remain authoritative."
    )

    return _ai_shell(
        status="ok",
        used=True,
        overall=final_overall,
        per_criterion=per_criterion,
        source_refs=refs,
        reasons=reasons,
        clamped=clamped,
        rubric=rubric,
        provider=cfg.provider,
        model=cfg.model,
    )
