"""Shared test fixtures.

Tests must never pick up the developer's real ``.env`` (it may contain a live
Groq key and different folder paths), so the env file is disabled for the whole
session and settings caches are reset between tests.
"""
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Must be set before app.config is imported anywhere.
os.environ.setdefault("DOCUMENT_MANAGER_ENV_FILE", "")


@pytest.fixture(autouse=True)
def clean_settings_cache():
    """Reset the settings and model-config caches around every test."""
    from app.config import reset_settings
    from app.services.ai_service import reset_capability_cache
    from app.services.model_config import reset_model_config

    reset_settings()
    reset_model_config()
    reset_capability_cache()
    yield
    reset_settings()
    reset_model_config()
    reset_capability_cache()


@pytest.fixture
def groq_settings():
    """Settings object configured for Groq with a dummy key."""
    from app.config import Settings

    return Settings(
        ai_provider="groq",
        groq_api_key="gsk_test_key",
        chat_model="openai/gpt-oss-120b",
        analysis_model="openai/gpt-oss-120b",
        vision_model="qwen/qwen3.6-27b",
        embedding_provider="local",
        ocr_engine="auto",
        reasoning_effort="medium",
    )
