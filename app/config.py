import os
import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Any
from sqlalchemy.orm import Session

class Settings(BaseSettings):
    # Database
    database_url: str = "sqlite:///./data/documents.db"

    # AI Provider: "groq", "openai" or "azure"
    ai_provider: str = "groq"

    # Groq (OpenAI-compatible endpoint)
    groq_api_key: Optional[str] = None
    # A second key on a different account. Groq's free tier caps both requests
    # per minute and tokens per day, and hitting either stops every AI feature
    # in the product at once - classification, summaries, the assistant. When
    # the first key is refused for quota, the next request goes out on this one
    # instead of failing. Leave it unset and behaviour is exactly as before.
    groq_api_key_2: Optional[str] = None
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # OpenAI
    openai_api_key: Optional[str] = None
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "openai/gpt-oss-120b"
    analysis_model: str = "openai/gpt-oss-120b"
    vision_model: str = "qwen/qwen3.6-27b"

    # Azure OpenAI
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_version: str = "2024-08-01-preview"
    azure_openai_chat_deployment: str = ""
    azure_openai_embeddings_deployment: str = ""

    # Embeddings. Groq has no embeddings endpoint, so "local" (ONNX MiniLM,
    # CPU, 384 dimensions) is the default. Switch to "openai"/"azure" only if
    # you have a key for that provider, then re-run reindex-vectors --force.
    embedding_provider: str = "local"
    local_embedding_model: str = "all-MiniLM-L6-v2"

    # OCR engine selection: "auto" | "vision" | "tesseract"
    ocr_engine: str = "auto"
    vision_ocr_enabled: bool = True
    vision_max_pages: int = 20
    vision_max_image_bytes: int = 4 * 1024 * 1024
    pdf_text_layer_first: bool = True

    # Generation tuning
    reasoning_effort: str = "medium"
    ai_temperature_extraction: float = 0.1
    ai_temperature_chat: float = 0.3
    ai_max_tokens_extraction: int = 4096
    # Groq counts (prompt + max_tokens) against the per-minute token limit, and
    # the vision model's free tier is only 8000 TPM. Keep the vision budget low.
    ai_max_tokens_chat: int = 4096
    ai_max_tokens_vision: int = 2048

    # ChromaDB
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection_name: str = "documents"

    # File paths
    root_folder: Optional[str] = None
    staging_folder: str = "./data/staging"
    data_folder: str = "./data"
    storage_folder: str = "./data/storage"
    logs_folder: str = "./data/logs"
    backup_folder: str = "./data/backups"

    # OCR
    tesseract_path: str = "/usr/bin/tesseract"
    poppler_path: str = "/usr/bin"

    # File settings
    max_file_size: str = "100MB"
    allowed_extensions: str = "pdf,png,jpg,jpeg,tiff,bmp,txt,text,md,markdown"

    # Security
    # Do NOT ship a static, well-known default secret_key. Anything signed
    # with this key would be forgeable by anyone who has read the source.
    # When unset, a per-process random key is generated; admins should
    # configure a stable value via the database settings table (the
    # DatabaseSettings loader will override this).
    secret_key: str = secrets.token_urlsafe(32)
    jwt_secret_key: Optional[str] = None  # JWT secret key for authentication
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    environment: str = "development"
    production_mode: bool = False  # Set to True in production for secure cookies
    cors_origins: str = "http://localhost:3000,http://localhost:8000,http://127.0.0.1:8000"
    trusted_proxy_ips: str = "127.0.0.1,::1"

    # Logging
    log_level: str = "INFO"

    # AI Service
    ai_text_limit: int = 16000
    ai_context_limit: int = 10000
    ai_request_timeout: int = 60  # Timeout for AI requests in seconds
    ai_max_retries: int = 2  # Maximum number of retries for failed AI requests

    model_config = SettingsConfigDict(
        # Runtime values may be supplied by Docker/Kubernetes environment
        # variables, or by a local .env file for development. Real environment
        # variables take precedence over .env; database-backed settings then
        # override both.
        case_sensitive=False,
        env_file=os.getenv("DOCUMENT_MANAGER_ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        env_prefix=""
    )

    def model_post_init(self, __context: Any) -> None:
        # Apply config/models.json on top of the code defaults, but never on
        # top of an explicitly supplied value (env var or constructor kwarg).
        # Effective precedence: code default < models.json < env < database.
        self._apply_model_config_defaults()

        # Keep the existing ENVIRONMENT=production setup contract while still
        # allowing an explicit PRODUCTION_MODE value to override it.
        if "production_mode" not in self.model_fields_set:
            self.production_mode = self.environment.lower() == "production"

    def _apply_model_config_defaults(self) -> None:
        """Overlay values from ``config/models.json`` onto unset fields."""
        try:
            from .services.model_config import as_settings_overrides

            overrides = as_settings_overrides()
        except Exception as exc:  # pragma: no cover - defensive only
            from loguru import logger

            logger.warning(f"Could not apply model config defaults: {exc}")
            return

        for key, value in overrides.items():
            if key in self.model_fields_set:
                continue  # explicit env/kwarg wins
            if not hasattr(self, key):
                continue
            try:
                object.__setattr__(self, key, value)
            except Exception:  # pragma: no cover - defensive only
                continue

    @property
    def allowed_extensions_list(self) -> list:
        return [ext.strip().lower() for ext in self.allowed_extensions.split(",")]

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def trusted_proxy_ips_list(self) -> list[str]:
        return [ip.strip() for ip in self.trusted_proxy_ips.split(",") if ip.strip()]

    @property
    def max_file_size_bytes(self) -> int:
        size_str = self.max_file_size.upper()
        if size_str.endswith("MB"):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith("GB"):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        else:
            return int(size_str)

    @property
    def data_dir(self) -> str:
        return self.data_folder

    @property
    def active_api_key(self) -> Optional[str]:
        """API key for the currently selected chat/vision provider."""
        provider = (self.ai_provider or "").lower()
        if provider == "groq":
            return self.groq_api_key
        if provider == "azure":
            return self.azure_openai_api_key
        return self.openai_api_key

    @property
    def vision_available(self) -> bool:
        """True when a vision-capable model can actually be called."""
        return bool(
            self.vision_ocr_enabled
            and self.ocr_engine in ("auto", "vision")
            and self.vision_model
            and self.active_api_key
        )

class DatabaseSettings(Settings):
    """Settings that loads configuration from database"""

    def __init__(self, db: Session = None, **kwargs):
        # Load defaults, .env and runtime environment variables first.
        # Persisted application settings take precedence when a database is
        # available.
        super().__init__(**kwargs)

        # Then override with database values if available
        if db:
            self._load_from_database(db)

    def _load_from_database(self, db: Session):
        """Load settings from database"""
        from .models import Settings as SettingsModel

        # Get all settings from database
        db_settings = db.query(SettingsModel).all()

        # Convert to dict
        settings_dict = {setting.key: setting.value for setting in db_settings}

        # Update instance attributes
        for key, value in settings_dict.items():
            if hasattr(self, key):
                # Try to preserve type
                attr_value = getattr(self, key)
                try:
                    if isinstance(attr_value, bool):
                        setattr(self, key, str(value).lower() in ('true', '1', 'yes'))
                    elif isinstance(attr_value, int):
                        setattr(self, key, int(value))
                    elif isinstance(attr_value, float):
                        setattr(self, key, float(value))
                    else:
                        # For optional string fields, don't set empty strings
                        if value or not key.endswith('_api_key'):
                            setattr(self, key, value)
                except (ValueError, AttributeError, TypeError):
                    setattr(self, key, value)

    def save_to_database(self, db: Session, key: str, value: Any):
        """Save a single setting to database"""
        from .models import Settings as SettingsModel

        # Check if setting exists
        setting = db.query(SettingsModel).filter(SettingsModel.key == key).first()

        if setting:
            setting.value = str(value)
        else:
            setting = SettingsModel(key=key, value=str(value))
            db.add(setting)

        db.commit()

    def save_all_to_database(self, db: Session):
        """Save all current settings to database"""

        # Get all fields
        for field_name, field_value in self.__dict__.items():
            if not field_name.startswith('_'):
                self.save_to_database(db, field_name, field_value)

# Global settings instance
_settings = None

def get_settings(db: Session = None) -> Settings:
    """Get settings instance, optionally loading from database"""
    global _settings

    # If db is provided, always create fresh instance to get latest values
    if db:
        return DatabaseSettings(db=db)

    # Otherwise use cached instance
    if _settings is None:
        _settings = Settings()

    return _settings

def reset_settings():
    """Reset the global settings instance"""
    global _settings
    _settings = None

    # Also drop the model-config cache so an edited config/models.json is
    # picked up by the next get_settings() call.
    try:
        from .services.model_config import reset_model_config

        reset_model_config()
    except Exception:  # pragma: no cover - defensive only
        pass
