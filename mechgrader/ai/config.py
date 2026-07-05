"""Environment-driven configuration + the global AI kill switch.

Credentials and provider selection are read from the environment ONLY -- a key
is never hardcoded, defaulted to a literal, or written anywhere. Reading goes
through a small indirection (an ``env`` mapping) so tests can pass an explicit,
hermetic environment instead of mutating ``os.environ`` (and so nothing leaks in
from the developer's real shell).

Kill switch (AI-OFF). The grader must run fully WITHOUT an API key. AI is OFF --
and NO network call is made -- when ANY of these hold:

* ``MECHGRADER_LLM_PROVIDER`` is unset / empty / "none" (case-insensitive);
* ``MECHGRADER_AI_DISABLED`` is set truthy;
* no ``MECHGRADER_LLM_API_KEY`` is present.

Only ``MECHGRADER_LLM_{PROVIDER,API_KEY,MODEL}`` are credentials/selection. The
extra ``MECHGRADER_LLM_{BASE_URL,TIMEOUT,MAX_RETRIES}`` knobs are non-secret
operational overrides (also env-only) with safe defaults; the base URLs below
are public API roots, not secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional

__all__ = [
    "ENV_PROVIDER",
    "ENV_API_KEY",
    "ENV_MODEL",
    "ENV_DISABLED",
    "ENV_BASE_URL",
    "ENV_TIMEOUT",
    "ENV_MAX_RETRIES",
    "DEFAULT_BASE_URLS",
    "DEFAULT_MODELS",
    "DEFAULT_TIMEOUT",
    "DEFAULT_MAX_RETRIES",
    "AiConfig",
    "load_config",
    "is_truthy",
    "provider_family",
]

# Credential / selection env vars (the only ones that carry secrets or choose a
# provider). NEVER hardcode a value for these.
ENV_PROVIDER = "MECHGRADER_LLM_PROVIDER"
ENV_API_KEY = "MECHGRADER_LLM_API_KEY"
ENV_MODEL = "MECHGRADER_LLM_MODEL"
ENV_DISABLED = "MECHGRADER_AI_DISABLED"

# Non-secret operational overrides (safe to have defaults).
ENV_BASE_URL = "MECHGRADER_LLM_BASE_URL"
ENV_TIMEOUT = "MECHGRADER_LLM_TIMEOUT"
ENV_MAX_RETRIES = "MECHGRADER_LLM_MAX_RETRIES"

# A provider string in this set means "AI off" (no provider chosen).
_OFF_PROVIDERS = {"", "none", "off", "disabled", "false", "0"}
_TRUTHY = {"1", "true", "yes", "on", "y", "t"}

#: Public API roots (NOT secrets), overridable with ``MECHGRADER_LLM_BASE_URL``.
DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
}
#: Fallback model per provider family, used ONLY when the env model is empty so a
#: real request is still well-formed. Never presented as a graded measurement.
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-latest",
}

DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_RETRIES = 2  # retries AFTER the first attempt (bounded)


def is_truthy(value: Optional[str]) -> bool:
    """True for ``1/true/yes/on/y/t`` (case-insensitive); False otherwise/None."""
    return bool(value) and value.strip().lower() in _TRUTHY


def provider_family(provider: str) -> str:
    """Collapse a raw provider string to a supported family ("openai"/"anthropic").

    Unknown non-empty providers are returned as-is: per the kill-switch rule they
    still count as "enabled" (provider set + key present), and fail *gracefully*
    to the deterministic fallback later rather than being silently rewritten.
    """
    p = (provider or "").strip().lower()
    if p in {
        "openai",
        "openai-compatible",
        "openai_compatible",
        "compatible",
        "oai",
        "azure",
        "azure-openai",
        "azure_openai",
        "together",
        "groq",
        "openrouter",
        "vllm",
        "ollama",
    }:
        return "openai"
    if p in {"anthropic", "claude", "anthropic-messages"}:
        return "anthropic"
    return p


def _as_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AiConfig:
    """Resolved AI configuration + the kill-switch decision.

    ``provider`` is the raw env string (kept verbatim for reporting); ``family``
    maps it to a supported request shape. ``enabled`` is the single source of
    truth for whether an LLM call may be attempted at all.
    """

    provider: str
    api_key: str
    model: str
    base_url: str
    disabled_flag: bool
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = DEFAULT_MAX_RETRIES

    @property
    def family(self) -> str:
        return provider_family(self.provider)

    @property
    def off_reason(self) -> Optional[str]:
        """Human-readable reason AI is off, or ``None`` when it is enabled."""
        if self.disabled_flag:
            return f"{ENV_DISABLED} is set truthy - AI grading disabled"
        if (self.provider or "").strip().lower() in _OFF_PROVIDERS:
            return f"{ENV_PROVIDER} is unset/none - AI grading disabled"
        if not self.api_key:
            return f"no {ENV_API_KEY} present - AI grading disabled"
        return None

    @property
    def enabled(self) -> bool:
        return self.off_reason is None


def load_config(env: Optional[Mapping[str, str]] = None) -> AiConfig:
    """Build an :class:`AiConfig` from ``env`` (defaults to ``os.environ``).

    Never raises; malformed numeric knobs fall back to their defaults. The API
    key is read but never logged, echoed, or defaulted.
    """
    src: Mapping[str, str] = os.environ if env is None else env

    def get(name: str) -> str:
        val = src.get(name)
        return val.strip() if isinstance(val, str) else ""

    provider = get(ENV_PROVIDER)
    api_key = get(ENV_API_KEY)
    model = get(ENV_MODEL)
    family = provider_family(provider)

    base_url = get(ENV_BASE_URL) or DEFAULT_BASE_URLS.get(family, "")
    if not model:
        model = DEFAULT_MODELS.get(family, "")

    disabled_flag = is_truthy(src.get(ENV_DISABLED) if isinstance(src.get(ENV_DISABLED), str) else None)
    timeout = _as_float(get(ENV_TIMEOUT), DEFAULT_TIMEOUT)
    max_retries = max(0, _as_int(get(ENV_MAX_RETRIES), DEFAULT_MAX_RETRIES))

    return AiConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url.rstrip("/"),
        disabled_flag=disabled_flag,
        timeout=timeout,
        max_retries=max_retries,
    )
