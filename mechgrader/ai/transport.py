"""Stdlib HTTP transport + provider request/response adapters.

Real network calls go through :class:`UrllibTransport`, which uses ONLY the
Python standard library (``urllib.request``) -- there is no third-party HTTP
dependency to pip install. The transport is injectable: anything with a
``post(url, *, headers, body, timeout) -> str`` method works, so tests hand in a
fake and NO socket is ever opened.

Two provider families are supported, selected by ``config.family``:

* ``openai``    -- OpenAI-compatible ``/chat/completions`` (Bearer auth);
* ``anthropic`` -- Anthropic ``/v1/messages`` (``x-api-key`` + version header).

Only the request envelope and the content extraction differ between them; the
rubric prompt and all parsing/validation around it are identical. ``LlmClient``
ties a config + transport together behind a single ``complete(system, user)``
call that returns the model's raw text (expected to be a JSON rubric verdict).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "TransportError",
    "LlmError",
    "HttpTransport",
    "UrllibTransport",
    "LlmClient",
    "build_request",
    "extract_text",
    "ANTHROPIC_VERSION",
]

ANTHROPIC_VERSION = "2023-06-01"


class TransportError(RuntimeError):
    """A network-level failure (offline, timeout, HTTP error, rate limit).

    ``status`` carries the HTTP status code when there was one (e.g. 429 for a
    rate limit), else ``None``. These are treated as "provider unavailable" and
    trigger a graceful fallback to the deterministic grade.
    """

    def __init__(self, message: str, *, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


class LlmError(RuntimeError):
    """The provider responded, but not in a shape we can read (bad envelope)."""


class HttpTransport:
    """Structural interface: ``post`` returns the response body as text.

    Concrete transports (and test fakes) implement ``post``; this base exists for
    documentation and isinstance-free duck typing.
    """

    def post(self, url: str, *, headers: Dict[str, str], body: bytes, timeout: float) -> str:
        raise NotImplementedError


class UrllibTransport(HttpTransport):
    """HTTP POST via ``urllib.request`` (stdlib only)."""

    def post(self, url: str, *, headers: Dict[str, str], body: bytes, timeout: float) -> str:
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, "replace")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:500]
            except Exception:  # pragma: no cover - defensive; body may be unreadable
                detail = ""
            raise TransportError(
                f"provider returned HTTP {exc.code}: {detail}", status=exc.code
            ) from exc
        except urllib.error.URLError as exc:
            raise TransportError(f"could not reach provider: {exc.reason}") from exc
        except (TimeoutError, OSError) as exc:  # pragma: no cover - environment dependent
            raise TransportError(f"network error contacting provider: {exc}") from exc


def build_request(config: Any, system: str, user: str) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
    """Build ``(url, headers, json_payload)`` for ``config.family``.

    Raises :class:`LlmError` for an unsupported provider family so the caller can
    fall back gracefully rather than emitting a malformed request.
    """
    family = config.family
    if family == "openai":
        url = f"{config.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # Ask compatible endpoints to emit a bare JSON object; harmless if ignored.
            "response_format": {"type": "json_object"},
        }
        return url, headers, payload

    if family == "anthropic":
        url = f"{config.base_url}/v1/messages"
        headers = {
            "x-api-key": config.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        payload = {
            "model": config.model,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        }
        return url, headers, payload

    raise LlmError(
        f"unsupported LLM provider family {family!r} (from provider {config.provider!r})"
    )


def extract_text(config: Any, response: Dict[str, Any]) -> str:
    """Pull the assistant's text out of a provider response envelope."""
    family = config.family
    try:
        if family == "openai":
            content = response["choices"][0]["message"]["content"]
        elif family == "anthropic":
            blocks = response["content"]
            content = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
        else:  # pragma: no cover - build_request already rejected this family
            raise LlmError(f"unsupported LLM provider family {family!r}")
    except (KeyError, IndexError, TypeError) as exc:
        raise LlmError("unexpected provider response shape") from exc

    if isinstance(content, list):  # some gateways return content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        raise LlmError("provider returned non-text content")
    return content


class LlmClient:
    """Provider-agnostic client exposing ``complete(system, user) -> text``.

    The transport is injectable (defaulting to :class:`UrllibTransport`) so the
    real HTTP path itself is testable with a fake, and so no network is required
    to construct a client.
    """

    def __init__(self, config: Any, transport: Optional[HttpTransport] = None) -> None:
        self.config = config
        self.transport = transport or UrllibTransport()

    def complete(self, system: str, user: str) -> str:
        url, headers, payload = build_request(self.config, system, user)
        body = json.dumps(payload).encode("utf-8")
        text = self.transport.post(
            url, headers=headers, body=body, timeout=self.config.timeout
        )
        try:
            response = json.loads(text)
        except (ValueError, TypeError) as exc:
            raise LlmError("provider returned a non-JSON body") from exc
        return extract_text(self.config, response)
