"""Tests for config/models.json loading and the settings precedence chain."""
import json

import pytest

from app.config import Settings
from app.services import model_config as mc


def write_config(tmp_path, payload) -> str:
    path = tmp_path / "models.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_repository_config_file_is_valid_and_selects_groq():
    """The shipped config/models.json must parse and target Groq."""
    config = mc.load_model_config(force=True)

    assert config["active_provider"] == "groq"
    assert config["models"]["chat"] == "openai/gpt-oss-120b"
    assert config["models"]["analysis"] == "openai/gpt-oss-120b"
    assert config["models"]["vision"] == "qwen/qwen3.6-27b"
    assert config["embeddings"]["provider"] == "local"


def test_readme_keys_are_stripped():
    config = mc.load_model_config(force=True)
    assert "_readme" not in config
    assert "_readme" not in config["embeddings"]
    assert "_readme" not in config["ocr"]


def test_settings_pick_up_model_config(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "MODEL_CONFIG_FILE",
        write_config(
            tmp_path,
            {
                "active_provider": "groq",
                "models": {
                    "chat": "custom/chat-model",
                    "analysis": "custom/analysis-model",
                    "vision": "custom/vision-model",
                },
            },
        ),
    )
    mc.reset_model_config()

    settings = Settings()

    assert settings.chat_model == "custom/chat-model"
    assert settings.analysis_model == "custom/analysis-model"
    assert settings.vision_model == "custom/vision-model"


def test_environment_variable_beats_config_file(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "MODEL_CONFIG_FILE",
        write_config(tmp_path, {"models": {"chat": "from-file"}}),
    )
    monkeypatch.setenv("CHAT_MODEL", "from-environment")
    mc.reset_model_config()

    assert Settings().chat_model == "from-environment"


def test_constructor_argument_beats_config_file(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "MODEL_CONFIG_FILE",
        write_config(tmp_path, {"models": {"chat": "from-file"}}),
    )
    mc.reset_model_config()

    assert Settings(chat_model="explicit").chat_model == "explicit"


def test_missing_config_file_falls_back_to_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_CONFIG_FILE", str(tmp_path / "does-not-exist.json"))
    mc.reset_model_config()

    config = mc.load_model_config(force=True)
    assert config["models"]["chat"] == mc.DEFAULT_CONFIG["models"]["chat"]


def test_malformed_config_file_falls_back_to_defaults(monkeypatch, tmp_path):
    broken = tmp_path / "models.json"
    broken.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setenv("MODEL_CONFIG_FILE", str(broken))
    mc.reset_model_config()

    config = mc.load_model_config(force=True)
    assert config["active_provider"] == "groq"
    assert config["models"]["vision"] == mc.DEFAULT_CONFIG["models"]["vision"]


@pytest.mark.parametrize(
    "field,bad_value,expected",
    [
        ("active_provider", "not-a-provider", "groq"),
        ("embeddings", {"provider": "nonsense"}, "local"),
        ("ocr", {"engine": "nonsense"}, "auto"),
        ("generation", {"reasoning_effort": "extreme"}, "medium"),
    ],
)
def test_invalid_values_are_clamped(monkeypatch, tmp_path, field, bad_value, expected):
    monkeypatch.setenv("MODEL_CONFIG_FILE", write_config(tmp_path, {field: bad_value}))
    mc.reset_model_config()

    config = mc.load_model_config(force=True)

    if field == "active_provider":
        assert config["active_provider"] == expected
    elif field == "embeddings":
        assert config["embeddings"]["provider"] == expected
    elif field == "ocr":
        assert config["ocr"]["engine"] == expected
    else:
        assert config["generation"]["reasoning_effort"] == expected


def test_config_file_is_reloaded_when_it_changes(monkeypatch, tmp_path):
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"models": {"chat": "first"}}), encoding="utf-8")
    monkeypatch.setenv("MODEL_CONFIG_FILE", str(path))
    mc.reset_model_config()

    assert mc.load_model_config()["models"]["chat"] == "first"

    # Rewrite with a different mtime.
    path.write_text(json.dumps({"models": {"chat": "second"}}), encoding="utf-8")
    os_stat = path.stat()
    import os as _os

    _os.utime(path, (os_stat.st_atime, os_stat.st_mtime + 10))

    assert mc.load_model_config()["models"]["chat"] == "second"


def test_model_keys_are_never_seeded_into_the_database(tmp_path):
    """Seeding model keys would permanently shadow config/models.json."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.models import Base, Settings as SettingsModel
    from app.utils.init_settings import MODEL_CONFIG_KEYS, initialize_default_settings

    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        created = initialize_default_settings(db)
        stored = {row.key for row in db.query(SettingsModel).all()}

    leaked = stored & MODEL_CONFIG_KEYS
    assert not leaked, f"model keys must not be seeded: {sorted(leaked)}"
    assert not set(created) & MODEL_CONFIG_KEYS

    # Folder settings must still be seeded.
    assert "staging_folder" in stored
    assert "storage_folder" in stored


def test_every_model_config_key_is_a_real_settings_field():
    from app.config import Settings
    from app.utils.init_settings import MODEL_CONFIG_KEYS

    unknown = MODEL_CONFIG_KEYS - set(Settings.model_fields.keys())
    assert not unknown, f"MODEL_CONFIG_KEYS lists unknown fields: {unknown}"


def test_overrides_and_model_config_keys_agree():
    """as_settings_overrides() and MODEL_CONFIG_KEYS must cover the same keys."""
    from app.utils.init_settings import MODEL_CONFIG_KEYS

    override_keys = set(mc.as_settings_overrides())
    missing = override_keys - MODEL_CONFIG_KEYS
    assert not missing, (
        "these keys come from models.json but are not protected from seeding: "
        f"{sorted(missing)}"
    )


def test_as_settings_overrides_is_flat_and_complete():
    overrides = mc.as_settings_overrides()

    expected_keys = {
        "ai_provider",
        "chat_model",
        "analysis_model",
        "vision_model",
        "embedding_provider",
        "local_embedding_model",
        "ocr_engine",
        "reasoning_effort",
    }
    assert expected_keys.issubset(overrides.keys())

    # Every override key must be a real Settings field, otherwise the overlay
    # silently drops it.
    field_names = set(Settings.model_fields.keys())
    unknown = set(overrides) - field_names
    assert not unknown, f"models.json maps to unknown Settings fields: {unknown}"
