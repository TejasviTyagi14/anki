"""The card-generation SEAM: turn a registered source into candidate MechCards.

This is the ONE part of the 7f pipeline that needs an LLM (and therefore an API
key). It is deliberately a thin, documented seam:

* **Key-gated.** Configuration is read from the environment (``MECHGRADER_LLM_*``),
  mirroring how the chem-grader AI grader reads ``OPENAI_*``. No key is ever
  hard-coded, and with the default client a missing key raises *before* any
  network call is attempted.
* **stdlib only.** The default transport uses :mod:`urllib.request` — no third-
  party HTTP dependency — so it runs anywhere the rest of MechGrader runs.
* **Injectable.** ``generate_cards`` takes a ``client`` callable, so callers (and
  tests) can supply a fake transport. The prompt-building and response-parsing
  helpers are pure functions and are unit-tested offline. **Tests never call a
  real API**, and this module never runs as an import side effect.

Typical real use (NOT exercised by the test suite)::

    export MECHGRADER_LLM_API_KEY=sk-...
    export MECHGRADER_LLM_MODEL=gpt-4o          # optional
    export MECHGRADER_LLM_BASE_URL=https://api.openai.com/v1   # optional
    python -c "from mechgrader.cardgen.generate import generate_cards; ..."

The generated cards are then fed to :func:`mechgrader.cardgen.check.run_cardgen_check`
against the gold set; only cards that clear the pre-registered cutoff may ship,
and every card must still cite a source registered in ``sources/registry.json``
before :func:`mechgrader.notetype.mechcard.add_mechcard` will accept it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Optional

__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "LLMConfig",
    "GenerationConfigError",
    "GenerationError",
    "GenerationClient",
    "build_generation_messages",
    "parse_generated_cards",
    "default_urllib_client",
    "generate_cards",
]

DEFAULT_MODEL = "gpt-4o"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 90.0


class GenerationConfigError(RuntimeError):
    """The generator is not configured (e.g. no API key). Nothing was sent."""


class GenerationError(RuntimeError):
    """The generation call or its parsing failed."""


@dataclass(frozen=True)
class LLMConfig:
    """LLM connection settings, read from ``MECHGRADER_LLM_*`` by default.

    Kept as a value object so tests can construct one explicitly (e.g. with an
    empty ``api_key`` to exercise the key-gate) without touching the process
    environment.
    """

    api_key: str = ""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout: float = DEFAULT_TIMEOUT

    @classmethod
    def from_env(cls, env: Optional[dict] = None) -> "LLMConfig":
        """Build a config from the environment (``os.environ`` by default).

        Reads ``MECHGRADER_LLM_API_KEY`` / ``MECHGRADER_LLM_BASE_URL`` /
        ``MECHGRADER_LLM_MODEL`` / ``MECHGRADER_LLM_TIMEOUT``. The key is never
        logged or embedded anywhere; it lives only in this object.
        """
        source = os.environ if env is None else env
        api_key = str(source.get("MECHGRADER_LLM_API_KEY", "")).strip()
        base_url = str(source.get("MECHGRADER_LLM_BASE_URL", DEFAULT_BASE_URL)).strip().rstrip("/")
        model = str(source.get("MECHGRADER_LLM_MODEL", DEFAULT_MODEL)).strip()
        raw_timeout = str(source.get("MECHGRADER_LLM_TIMEOUT", "")).strip()
        try:
            timeout = float(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT
        except ValueError:
            timeout = DEFAULT_TIMEOUT
        return cls(api_key=api_key, base_url=base_url or DEFAULT_BASE_URL, model=model or DEFAULT_MODEL, timeout=timeout)


#: A transport: ``(messages, config) -> raw_model_text``. The default is
#: :func:`default_urllib_client`; tests inject a fake so no network is touched.
GenerationClient = Callable[[list, LLMConfig], str]


GENERATION_SYSTEM_PROMPT = """\
You write organic-chemistry flashcards for MCAT students, grounded ONLY in the \
provided source text. Each card tests exactly ONE mechanism fact.

Rules:
- Do NOT invent facts. If the source does not support a fact, do not write a card \
about it. A wrong card is worse than no card.
- Prefer "why/how" mechanism questions over trivia; never give away the answer in \
the question; no duplicates.
- Keep the answer to a short, checkable phrase.

Respond with a SINGLE JSON object and nothing else:
  {"cards": [{"question": str, "answer": str, "source_ref": str}, ...]}
where source_ref echoes the provided source_ref verbatim.
"""


def build_generation_messages(
    source_text: str,
    *,
    n: int,
    source_ref: Optional[str] = None,
    reaction_type: Optional[str] = None,
) -> list:
    """Assemble the chat messages for a generation request (pure function).

    Kept separate from the transport so the prompt contract can be tested
    offline. Does not touch the network or any key.
    """
    header = [f"Write {int(n)} flashcards from the SOURCE below."]
    if source_ref:
        header.append(f"source_ref (echo verbatim into every card): {source_ref}")
    if reaction_type:
        header.append(f"Focus on the reaction type: {reaction_type}")
    user = "\n".join(header) + "\n\nSOURCE:\n" + (source_text or "").strip()
    return [
        {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def parse_generated_cards(raw_text: str) -> list:
    """Parse a model response into a list of card dicts (pure function).

    Accepts either a bare JSON list, a ``{"cards": [...]}`` object, or such JSON
    embedded in surrounding prose/code fences. Raises :class:`GenerationError`
    if no card list can be recovered.
    """
    text = (raw_text or "").strip()

    def _coerce(obj: Any) -> Optional[list]:
        if isinstance(obj, list):
            return [c for c in obj if isinstance(c, dict)]
        if isinstance(obj, dict) and isinstance(obj.get("cards"), list):
            return [c for c in obj["cards"] if isinstance(c, dict)]
        return None

    try:
        coerced = _coerce(json.loads(text))
        if coerced is not None:
            return coerced
    except (ValueError, TypeError):
        pass

    # Fall back to the widest {...} or [...] span embedded in the text.
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = text.find(open_ch), text.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            try:
                coerced = _coerce(json.loads(text[start : end + 1]))
                if coerced is not None:
                    return coerced
            except (ValueError, TypeError):
                continue

    raise GenerationError("could not parse a card list from the model response")


def default_urllib_client(messages: list, config: LLMConfig) -> str:
    """stdlib transport to an OpenAI-compatible chat endpoint.

    Uses :mod:`urllib.request` only. Imported lazily so importing this module has
    no network dependency. Raises :class:`GenerationConfigError` if there is no
    API key (so nothing is ever sent unauthenticated) and :class:`GenerationError`
    on transport/HTTP failures. **Not used in tests.**
    """
    import urllib.error
    import urllib.request

    if not config.api_key:
        raise GenerationConfigError(
            "No MECHGRADER_LLM_API_KEY set. Export a key before generating cards, "
            "e.g. export MECHGRADER_LLM_API_KEY=sk-...  (optionally "
            "MECHGRADER_LLM_MODEL / MECHGRADER_LLM_BASE_URL)."
        )

    payload = json.dumps(
        {
            "model": config.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:  # pragma: no cover - network path
        raise GenerationError(f"generation service error ({exc.code})") from exc
    except urllib.error.URLError as exc:  # pragma: no cover - network path
        raise GenerationError(f"could not reach the generation service: {exc.reason}") from exc

    try:
        data = json.loads(body)
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:  # pragma: no cover
        raise GenerationError("unexpected response shape from the generation service") from exc
    if isinstance(content, list):  # some gateways return content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content


def generate_cards(
    source_text: str,
    *,
    n: int = 10,
    source_ref: Optional[str] = None,
    reaction_type: Optional[str] = None,
    client: Optional[GenerationClient] = None,
    config: Optional[LLMConfig] = None,
) -> list:
    """Generate candidate MechCards from ``source_text`` via the LLM seam.

    ``client`` defaults to :func:`default_urllib_client`; inject a fake to run
    offline. ``config`` defaults to :meth:`LLMConfig.from_env`. With the default
    client a missing key raises :class:`GenerationConfigError` *before* any
    network call. Each returned card is a dict with at least ``question`` and
    ``answer``; ``source_ref`` is stamped on cards that omit it.

    The result is NOT trusted: pass it straight to
    :func:`mechgrader.cardgen.check.run_cardgen_check` before anything ships.
    """
    config = config or LLMConfig.from_env()
    client = client or default_urllib_client
    messages = build_generation_messages(
        source_text, n=n, source_ref=source_ref, reaction_type=reaction_type
    )
    raw = client(messages, config)
    cards = parse_generated_cards(raw)
    if source_ref:
        for card in cards:
            card.setdefault("source_ref", source_ref)
    return cards
