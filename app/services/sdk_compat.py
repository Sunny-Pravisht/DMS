"""Compatibility helpers for the ``openai`` SDK.

The SDK validates keyword arguments against an explicit signature and does not
accept ``**kwargs``. Server-side parameters that a given SDK build predates -
``max_completion_tokens`` on older releases, ``reasoning_effort`` on anything
before 1.59 - therefore raise ``TypeError`` locally before a request is ever
sent.

Groq accepts those fields in the JSON body, so anything the SDK does not
declare is forwarded through ``extra_body``. This keeps the application working
across a range of SDK versions instead of hard-pinning one.
"""
import inspect
import re
from functools import lru_cache
from typing import Any, Dict, Optional

from loguru import logger

# Hybrid reasoning models (Qwen among them) emit their chain of thought inline
# as <think>...</think> instead of using a separate response field. That text
# must never reach the OCR index or a user-facing answer.
_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_UNCLOSED_THINK = re.compile(r"<think\b[^>]*>.*\Z", re.DOTALL | re.IGNORECASE)


def strip_reasoning_blocks(text: str) -> str:
    """Remove inline <think> reasoning from a model response."""
    if not text or "<think" not in text.lower():
        return text

    cleaned = _THINK_BLOCK.sub("", text)
    # A truncated response can leave an unterminated block behind.
    cleaned = _UNCLOSED_THINK.sub("", cleaned)
    return cleaned.strip()


@lru_cache(maxsize=16)
def _supported_params_for(create_func) -> Optional[frozenset]:
    try:
        signature = inspect.signature(create_func)
    except (TypeError, ValueError):
        return None

    # A callable that accepts **kwargs needs no rewriting (test doubles).
    if any(p.kind == p.VAR_KEYWORD for p in signature.parameters.values()):
        return None

    return frozenset(
        name
        for name, param in signature.parameters.items()
        if name != "self" and param.kind is not param.VAR_POSITIONAL
    )


def supported_params(client) -> Optional[frozenset]:
    """Keyword arguments ``client.chat.completions.create`` accepts."""
    try:
        return _supported_params_for(type(client.chat.completions).create)
    except Exception:  # pragma: no cover - defensive only
        return None


def adapt_params(client, params: Dict[str, Any]) -> Dict[str, Any]:
    """Rewrite a request so the installed SDK accepts every key."""
    allowed = supported_params(client)
    if allowed is None:
        return params

    native: Dict[str, Any] = {}
    extra: Dict[str, Any] = {}
    for key, value in params.items():
        if key in allowed:
            native[key] = value
        else:
            extra[key] = value

    if extra:
        logger.debug(f"Forwarding unsupported SDK params via extra_body: {sorted(extra)}")
        merged = dict(native.get("extra_body") or {})
        merged.update(extra)
        native["extra_body"] = merged

    return native
