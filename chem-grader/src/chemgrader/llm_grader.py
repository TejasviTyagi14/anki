"""Vision grading of hand-drawn reactions via an OpenAI-compatible chat API.

Flow
----
The frontend turns the student's drawing into (1) a PNG snapshot and (2) a
machine-readable molecular graph, and POSTs both here. We:

1. Compute a deterministic RDKit **second opinion** — canonicalize the drawn
   product's SMILES and compare it to the (hidden) accepted answer(s). This is
   a cheap, trustworthy signal that complements the model.
2. Ask a vision-capable model to grade the *image* (spatial layout, cis/trans,
   wedge direction) together with the graph (authoritative for connectivity and
   charges), against the hidden reference answer, and to independently solve the
   problem itself ("give it a shot").
3. Parse and clamp the model's JSON into a stable feedback contract.

The company key is read from ``OPENAI_API_KEY`` and never leaves the server.
Endpoint/model are overridable with ``OPENAI_BASE_URL`` / ``OPENAI_MODEL``.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx

# ---- configuration (env-driven so the company key stays server-side) ------- #

DEFAULT_MODEL = "gpt-4o"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


def _config() -> tuple[str, str, str]:
    """(api_key, base_url, model), reading env each call so it's easy to change."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    model = os.environ.get("OPENAI_MODEL", DEFAULT_MODEL).strip()
    return api_key, base_url, model


class GraderConfigError(RuntimeError):
    """The grader isn't configured (e.g. no API key)."""


class GraderCallError(RuntimeError):
    """The upstream model call failed; the message is safe to show a student."""


# ---- prompt + output contract ---------------------------------------------- #

GRADE_KEYS = [
    "verdict",
    "score",
    "summary",
    "what_is_right",
    "what_is_wrong",
    "explanation",
    "study_tip",
    "model_answer",
]

GRADER_SYSTEM_PROMPT = """\
You are an organic chemistry teaching assistant grading a student's HAND-DRAWN \
answer to a reaction problem. Grade the chemistry, not the draftsmanship.

You receive:
- The problem statement.
- A PNG image of the student's drawing. In the image, y increases DOWNWARD. A \
solid wedge bond points toward the viewer with its NARROW end at the "from" atom; \
a hashed/dashed bond points away. Use the image as the authority for spatial \
layout, cis/trans geometry, and wedge/dash direction.
- A machine-readable molecular graph derived from the same drawing. Treat the \
graph as AUTHORITATIVE for connectivity, atom identity, formal charges, and bond \
orders (it lists per-molecule SMILES, formulas, atoms, and bonds, each tagged \
with a role: reactant / product / intermediate / structure).
- An independent cheminformatics check ("structure check") comparing the drawn \
product's canonical SMILES to the accepted answer — a strong hint, but reason for \
yourself; it can be blank if the drawing couldn't be parsed.
- Sometimes a hidden ANSWER KEY (the correct product, mechanism, and the wrong \
answers students commonly give). Reason independently; use the key to calibrate.

How to grade:
- Check that the drawn species actually answers what was asked: connectivity, \
regiochemistry, charges, degree of unsaturation, and — ONLY when the problem asks \
for it — stereochemistry (wedge/dash, cis/trans). If stereochemistry is not \
requested, do not penalize its absence.
- Accept chemically equivalent representations (condensed vs skeletal, either \
resonance form, atom ordering). When a product is chiral and the reaction is not \
stereospecific, accept either enantiomer but say so.
- Never invent atoms or bonds that aren't in the graph/image. If the drawing is \
ambiguous, name the ambiguity rather than guessing in the student's favor.
- Independently solve the problem yourself and report your own answer in \
"model_answer" (name + SMILES + one-line reasoning).

Scoring (integer 0-10):
- 10: flawless and complete.
- 7-9: essentially correct with a minor omission (e.g. a missing lone pair, an \
unlabeled reagent) — not a chemistry error.
- 4-6: one significant chemistry error (wrong regiochemistry, wrong functional \
group, missing requested stereochemistry).
- 1-3: on-topic but the main product is wrong.
- 0: blank, illegible, or unrelated.
Set verdict to "correct" for 9-10, "partially_correct" for 4-8, "incorrect" for 0-3.

Respond with a SINGLE JSON object and nothing else (no markdown, no code fences), \
with EXACTLY these keys:
  "verdict": one of "correct" | "partially_correct" | "incorrect"
  "score": integer 0-10
  "summary": one short sentence.
  "what_is_right": array of short strings (may be empty).
  "what_is_wrong": array of short strings (may be empty).
  "explanation": 2-5 sentences of reasoning; use \\n for line breaks.
  "study_tip": one actionable sentence.
  "model_answer": object { "name": string, "smiles": string, "reasoning": string } \
— YOUR OWN solution to the problem.
"""

HINT_BANNER = (
    "HINT MODE IS ON. Do NOT reveal or name the correct product anywhere in your "
    "response, and leave model_answer.name and model_answer.smiles as empty "
    'strings ("") — put only a gentle nudge in model_answer.reasoning. Point the '
    "student at what to reconsider (regiochemistry? stereochemistry? the "
    "nucleophile?) while keeping the verdict and score honest."
)


# ---- deterministic RDKit "second opinion" ---------------------------------- #

def second_opinion(payload: dict, expected_smiles: list[str], service) -> dict:
    """Compare the drawn product's canonical SMILES to the accepted answer(s).

    ``service`` is a :class:`~chemgrader.structure_service.StructureService`.
    Never raises — a drawing that can't be parsed just yields ``match=None``.
    """
    molecules = payload.get("molecules") or []
    # The "answer" is whatever the student drew as product; fall back to any
    # role when there are no arrows (a lone structure).
    drawn = [m for m in molecules if m.get("role") == "product"]
    if not drawn:
        drawn = [m for m in molecules if str(m.get("role", "")).startswith("structure")]
    if not drawn:
        drawn = molecules

    drawn_canon: list[str] = []
    for m in drawn:
        smi = (m or {}).get("smiles")
        if not smi:
            continue
        try:
            drawn_canon.append(service.canonical_smiles(smi))
        except Exception:
            # keep the raw string so the model still sees what was attempted
            drawn_canon.append(smi)

    ref_canon: list[str] = []
    for smi in expected_smiles or []:
        try:
            ref_canon.append(service.canonical_smiles(smi))
        except Exception:
            pass

    match: Optional[bool] = None
    if ref_canon and drawn_canon:
        match = any(d in ref_canon for d in drawn_canon)

    if not expected_smiles:
        note = "No answer key for this card; grade on chemistry alone."
    elif match is True:
        note = "The drawn product's connectivity matches an accepted answer."
    elif match is False:
        note = "The drawn product's connectivity does NOT match the accepted answer."
    else:
        note = "Could not parse a product from the drawing to compare."

    return {
        "drawn_product_smiles": drawn_canon,
        "reference_product_smiles": ref_canon,
        "connectivity_match": match,
        "note": note,
    }


# ---- request assembly ------------------------------------------------------ #

def build_user_text(
    statement: str,
    reference_answer: Optional[str],
    hint_mode: bool,
    payload: dict,
    second: dict,
    stereo_required: bool,
    freehand: bool = False,
) -> str:
    parts = [f"PROBLEM:\n{statement.strip()}"]
    parts.append(
        "STEREOCHEMISTRY: "
        + ("graded — the student was asked to show it." if stereo_required else "not required for this problem.")
    )
    if reference_answer and not hint_mode:
        parts.append(f"HIDDEN ANSWER KEY (do not quote verbatim):\n{reference_answer.strip()}")
    if hint_mode:
        parts.append(HINT_BANNER)
    if freehand:
        parts.append(
            "INPUT: This is a FREEHAND hand-drawn sketch — there is NO machine-readable "
            "graph. Read every structure, atom, bond order, formal charge, reaction arrow, "
            "reagent label, and wedge/dash stereobond directly from the image. Expect messy "
            "strokes, skeletal lines with implicit carbons and hydrogens, crossed-out work, "
            "and common shorthand (Me, Et, iPr, tBu, Ph, Ac, OH, X, R). If a region is "
            "genuinely illegible, say so and grade what you can rather than inventing atoms."
        )
    else:
        parts.append("STRUCTURE CHECK (independent RDKit):\n" + json.dumps(second, indent=2))
        parts.append("STUDENT DRAWING (machine-readable graph):\n" + json.dumps(payload, indent=2))
    return "\n\n".join(parts)


def _messages(system: str, user_text: str, image_b64: str) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
            ],
        },
    ]


def _api_error_message(status: int, body: str) -> str:
    if status == 401:
        return "The grading service rejected the API key (401). Check OPENAI_API_KEY on the server."
    if status == 403:
        return "The API key isn't allowed to use this model (403). Check the model name / your access."
    if status == 404:
        return "The model or endpoint was not found (404). Check OPENAI_MODEL / OPENAI_BASE_URL."
    if status == 429:
        return "Rate limited by the grading service (429). Wait a moment and try again."
    if status >= 500:
        return f"The grading service had an error ({status}). Try again shortly."
    # surface the upstream message when we can
    try:
        data = json.loads(body)
        msg = (data.get("error") or {}).get("message") or data.get("message")
        if msg:
            return f"Grading service error ({status}): {msg}"
    except Exception:
        pass
    return f"Grading service error ({status})."


# ---- parsing --------------------------------------------------------------- #

def extract_json(text: str) -> dict:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass
    raise GraderCallError("The grader returned a response that wasn't valid JSON.")


_VERDICTS = {"correct", "partially_correct", "incorrect"}


def _as_str(v: Any) -> str:
    return v if isinstance(v, str) else ("" if v is None else str(v))


def _as_str_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [_as_str(x) for x in v if _as_str(x).strip()]
    s = _as_str(v).strip()
    return [s] if s else []


def validate_grade(raw: dict, second: dict) -> dict:
    verdict = _as_str(raw.get("verdict")).lower().replace(" ", "_")
    if verdict not in _VERDICTS:
        verdict = "partially_correct"

    try:
        score = int(round(float(raw.get("score"))))
    except Exception:
        score = 0
    score = max(0, min(10, score))

    ma = raw.get("model_answer")
    if isinstance(ma, dict):
        model_answer = {
            "name": _as_str(ma.get("name")),
            "smiles": _as_str(ma.get("smiles")),
            "reasoning": _as_str(ma.get("reasoning")),
        }
    else:
        model_answer = {"name": "", "smiles": "", "reasoning": _as_str(ma)}

    return {
        "verdict": verdict,
        "score": score,
        "summary": _as_str(raw.get("summary")),
        "what_is_right": _as_str_list(raw.get("what_is_right")),
        "what_is_wrong": _as_str_list(raw.get("what_is_wrong")),
        "explanation": _as_str(raw.get("explanation")),
        "study_tip": _as_str(raw.get("study_tip")),
        "model_answer": model_answer,
        "structure_check": second,
    }


# ---- the call -------------------------------------------------------------- #

def grade_drawing(
    *,
    statement: str,
    reference_answer: Optional[str],
    expected_smiles: list[str],
    stereo_required: bool,
    image_png_base64: str,
    payload: dict,
    hint_mode: bool,
    service,
    freehand: bool = False,
    timeout: float = 90.0,
) -> dict:
    api_key, base_url, model = _config()
    if not api_key:
        raise GraderConfigError(
            "No OPENAI_API_KEY set on the server. Export your company key before starting "
            "the app, e.g.  export OPENAI_API_KEY=sk-...  (optionally OPENAI_MODEL / OPENAI_BASE_URL)."
        )

    if freehand:
        second = {
            "note": "Freehand sketch — graded from the image only (no automatic structure check).",
            "connectivity_match": None,
            "drawn_product_smiles": [],
            "reference_product_smiles": [],
        }
    else:
        second = second_opinion(payload, expected_smiles, service)
    user_text = build_user_text(statement, reference_answer, hint_mode, payload, second, stereo_required, freehand)
    messages = _messages(GRADER_SYSTEM_PROMPT, user_text, image_png_base64)

    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": 4000,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    url = f"{base_url}/chat/completions"

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, headers=headers, json=body)
            # Some models/gateways reject certain params. Adjust and retry once so
            # this works across gpt-4o, o-series/newer families, and company gateways.
            if resp.status_code == 400:
                txt = resp.text
                changed = False
                if "response_format" in txt and "response_format" in body:
                    body.pop("response_format", None)
                    changed = True
                if "temperature" in txt and "temperature" in body:
                    body.pop("temperature", None)
                    changed = True
                if "max_completion_tokens" in txt and "max_tokens" in body:
                    body["max_completion_tokens"] = body.pop("max_tokens")
                    changed = True
                if changed:
                    resp = client.post(url, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise GraderCallError(f"Could not reach the grading service: {exc}") from exc

    if resp.status_code != 200:
        raise GraderCallError(_api_error_message(resp.status_code, resp.text))

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise GraderCallError("The grading service returned an unexpected response shape.") from exc

    if isinstance(content, list):  # some vision models return content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))

    return validate_grade(extract_json(content), second)
