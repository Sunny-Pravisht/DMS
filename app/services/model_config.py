"""Loader for the central model configuration file (``config/models.json``).

This is the single place where model names live. The file is read lazily and
re-read automatically when its mtime changes, so editing it does not require a
restart for code paths that call :func:`get_model_config` per request.

Everything here is defensive on purpose: a malformed or missing config file must
never take the application down, it just falls back to the built-in defaults.
"""
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

# Repository root == parent of the ``app`` package.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "models.json"

# Built-in fallback. Mirrors config/models.json so the app still works if the
# file is deleted. Keep the two in sync when adding keys.
DEFAULT_CONFIG: Dict[str, Any] = {
    "active_provider": "groq",
    "models": {
        "chat": "openai/gpt-oss-120b",
        "analysis": "openai/gpt-oss-120b",
        "vision": "qwen/qwen3.6-27b",
    },
    "embeddings": {
        "provider": "local",
        "local_model": "all-MiniLM-L6-v2",
        "openai_model": "text-embedding-3-small",
        "azure_deployment": "",
    },
    "ocr": {
        "engine": "auto",
        "vision_enabled": True,
        "vision_max_pages": 20,
        "vision_max_image_bytes": 4 * 1024 * 1024,
        "pdf_text_layer_first": True,
    },
    "generation": {
        "reasoning_effort": "medium",
        "temperature_extraction": 0.1,
        "temperature_chat": 0.3,
        "max_tokens_extraction": 4096,
        # Groq counts (prompt + max_tokens) against the per-minute token limit.
        # The vision model's free-tier TPM is 8000, so this must stay small.
        "max_tokens_chat": 4096,
        "max_tokens_vision": 2048,
    },
    "providers": {
        "groq": {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key_env": "GROQ_API_KEY",
            "token_param": "max_completion_tokens",
            "supports_json_schema": True,
            "supports_temperature": True,
            "supports_reasoning_effort": True,
        },
        "openai": {
            "base_url": "",
            "api_key_env": "OPENAI_API_KEY",
            "token_param": "max_tokens",
            "supports_json_schema": True,
            "supports_temperature": True,
            "supports_reasoning_effort": False,
        },
        "azure": {
            "base_url": "",
            "api_key_env": "AZURE_OPENAI_API_KEY",
            "token_param": "max_completion_tokens",
            "supports_json_schema": True,
            "supports_temperature": False,
            "supports_reasoning_effort": False,
        },
    },
}

VALID_PROVIDERS = ("groq", "openai", "azure")
VALID_EMBEDDING_PROVIDERS = ("local", "openai", "azure")
VALID_OCR_ENGINES = ("auto", "vision", "tesseract")
VALID_REASONING_EFFORTS = ("none", "low", "medium", "high")

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None
_cache_mtime: Optional[float] = None
_cache_path: Optional[Path] = None


def get_config_path() -> Path:
    """Resolve the config file location (``MODEL_CONFIG_FILE`` overrides)."""
    override = os.getenv("MODEL_CONFIG_FILE")
    if override:
        return Path(override).expanduser()
    return _DEFAULT_CONFIG_PATH


def _strip_readme(value: Any) -> Any:
    """Drop the ``_readme``/``_comment`` documentation keys before merging."""
    if isinstance(value, dict):
        return {
            k: _strip_readme(v)
            for k, v in value.items()
            if not k.startswith("_")
        }
    return value


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``override`` onto a copy of ``base``."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


def _coerce_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _validate(config: Dict[str, Any]) -> Dict[str, Any]:
    """Clamp values to supported ranges, logging anything we correct."""
    provider = str(config.get("active_provider", "")).strip().lower()
    if provider not in VALID_PROVIDERS:
        logger.warning(
            f"models.json: unknown active_provider '{provider}', "
            f"falling back to '{DEFAULT_CONFIG['active_provider']}'"
        )
        provider = DEFAULT_CONFIG["active_provider"]
    config["active_provider"] = provider

    embeddings = config.setdefault("embeddings", {})
    emb_provider = str(embeddings.get("provider", "")).strip().lower()
    if emb_provider not in VALID_EMBEDDING_PROVIDERS:
        logger.warning(
            f"models.json: unknown embeddings.provider '{emb_provider}', using 'local'"
        )
        emb_provider = "local"
    embeddings["provider"] = emb_provider

    ocr = config.setdefault("ocr", {})
    engine = str(ocr.get("engine", "")).strip().lower()
    if engine not in VALID_OCR_ENGINES:
        logger.warning(f"models.json: unknown ocr.engine '{engine}', using 'auto'")
        engine = "auto"
    ocr["engine"] = engine
    ocr["vision_enabled"] = _coerce_bool(ocr.get("vision_enabled"), True)
    ocr["pdf_text_layer_first"] = _coerce_bool(ocr.get("pdf_text_layer_first"), True)
    ocr["vision_max_pages"] = max(1, _coerce_int(ocr.get("vision_max_pages"), 20))
    ocr["vision_max_image_bytes"] = max(
        64 * 1024, _coerce_int(ocr.get("vision_max_image_bytes"), 4 * 1024 * 1024)
    )

    generation = config.setdefault("generation", {})
    effort = str(generation.get("reasoning_effort", "")).strip().lower()
    if effort not in VALID_REASONING_EFFORTS:
        logger.warning(
            f"models.json: unknown generation.reasoning_effort '{effort}', using 'medium'"
        )
        effort = "medium"
    generation["reasoning_effort"] = effort
    defaults_gen = DEFAULT_CONFIG["generation"]
    for key in ("temperature_extraction", "temperature_chat"):
        generation[key] = min(
            2.0, max(0.0, _coerce_float(generation.get(key), defaults_gen[key]))
        )
    for key in ("max_tokens_extraction", "max_tokens_chat", "max_tokens_vision"):
        generation[key] = max(
            16, _coerce_int(generation.get(key), defaults_gen[key])
        )

    for name, spec in config.get("providers", {}).items():
        if not isinstance(spec, dict):
            continue
        default_spec = DEFAULT_CONFIG["providers"].get(name, {})
        for flag in (
            "supports_json_schema",
            "supports_temperature",
            "supports_reasoning_effort",
        ):
            spec[flag] = _coerce_bool(spec.get(flag), default_spec.get(flag, False))
        if spec.get("token_param") not in ("max_tokens", "max_completion_tokens"):
            spec["token_param"] = default_spec.get("token_param", "max_tokens")

    return config


def load_model_config(force: bool = False) -> Dict[str, Any]:
    """Return the merged model configuration, re-reading the file when it changes."""
    global _cache, _cache_mtime, _cache_path

    path = get_config_path()

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None

    with _lock:
        if (
            not force
            and _cache is not None
            and _cache_path == path
            and _cache_mtime == mtime
        ):
            return _cache

        merged = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy

        if mtime is None:
            logger.info(
                f"Model config file not found at {path}; using built-in defaults"
            )
        else:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
                if not isinstance(raw, dict):
                    raise ValueError("top-level value must be a JSON object")
                merged = _deep_merge(merged, _strip_readme(raw))
                logger.info(f"Loaded model configuration from {path}")
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                logger.error(
                    f"Failed to read model config {path}: {exc}. Using built-in defaults."
                )

        _cache = _validate(merged)
        _cache_mtime = mtime
        _cache_path = path
        return _cache


def reset_model_config() -> None:
    """Drop the cache (used by tests and by the settings reload path)."""
    global _cache, _cache_mtime, _cache_path
    with _lock:
        _cache = None
        _cache_mtime = None
        _cache_path = None


def provider_spec(provider: str) -> Dict[str, Any]:
    """Capability flags for a provider, falling back to sane defaults."""
    config = load_model_config()
    providers = config.get("providers", {})
    spec = providers.get((provider or "").lower())
    if isinstance(spec, dict):
        return spec
    return DEFAULT_CONFIG["providers"].get(
        (provider or "").lower(), DEFAULT_CONFIG["providers"]["openai"]
    )


def as_settings_overrides() -> Dict[str, Any]:
    """Flatten the config into ``Settings`` field names.

    Used both as the defaults source for :class:`app.config.Settings` and by
    ``cli.py sync-model-config`` to write the values into the database.
    """
    config = load_model_config()
    models = config.get("models", {})
    embeddings = config.get("embeddings", {})
    ocr = config.get("ocr", {})
    generation = config.get("generation", {})
    provider = config["active_provider"]
    spec = provider_spec(provider)

    return {
        "ai_provider": provider,
        "chat_model": models.get("chat", DEFAULT_CONFIG["models"]["chat"]),
        "analysis_model": models.get("analysis", DEFAULT_CONFIG["models"]["analysis"]),
        "vision_model": models.get("vision", DEFAULT_CONFIG["models"]["vision"]),
        "groq_base_url": spec.get("base_url", "")
        if provider == "groq"
        else DEFAULT_CONFIG["providers"]["groq"]["base_url"],
        "embedding_provider": embeddings.get("provider", "local"),
        "local_embedding_model": embeddings.get("local_model", "all-MiniLM-L6-v2"),
        "embedding_model": embeddings.get("openai_model", "text-embedding-3-small"),
        "ocr_engine": ocr.get("engine", "auto"),
        "vision_ocr_enabled": ocr.get("vision_enabled", True),
        "vision_max_pages": ocr.get("vision_max_pages", 20),
        "vision_max_image_bytes": ocr.get("vision_max_image_bytes", 4 * 1024 * 1024),
        "pdf_text_layer_first": ocr.get("pdf_text_layer_first", True),
        "reasoning_effort": generation.get("reasoning_effort", "medium"),
        "ai_temperature_extraction": generation.get("temperature_extraction", 0.1),
        "ai_temperature_chat": generation.get("temperature_chat", 0.3),
        "ai_max_tokens_extraction": generation.get("max_tokens_extraction", 4096),
        "ai_max_tokens_chat": generation.get("max_tokens_chat", 8192),
        "ai_max_tokens_vision": generation.get("max_tokens_vision", 8192),
    }
