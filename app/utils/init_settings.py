"""
Initialize default settings in the database
"""
from sqlalchemy.orm import Session
from ..models import Settings as SettingsModel
from ..config import Settings as DefaultSettings
from typing import Dict, Any

def initialize_default_settings(db: Session) -> Dict[str, Any]:
    """
    Initialize default settings in the database if they don't exist.
    Returns a dict of settings that were created.
    """
    # Define critical settings that must exist
    critical_settings = {
        'staging_folder': DefaultSettings().staging_folder,
        'data_folder': DefaultSettings().data_folder,
        'storage_folder': DefaultSettings().storage_folder,
        'logs_folder': DefaultSettings().logs_folder,
    }
    
    # Add other important settings.
    #
    # Model-related keys are deliberately NOT seeded here. Database rows sit at
    # the top of the precedence chain, so seeding them would permanently shadow
    # config/models.json and make editing that file look like it does nothing.
    # They are only written when an admin explicitly saves them in the UI or
    # runs `python cli.py sync-model-config`.
    defaults = DefaultSettings()
    other_settings = {
        'chroma_host': defaults.chroma_host,
        'chroma_port': str(defaults.chroma_port),
        'chroma_collection_name': defaults.chroma_collection_name,
        'tesseract_path': defaults.tesseract_path,
        'poppler_path': defaults.poppler_path,
        'max_file_size': defaults.max_file_size,
        'allowed_extensions': defaults.allowed_extensions,
        'log_level': defaults.log_level,
        'ai_text_limit': str(defaults.ai_text_limit),
        'ai_context_limit': str(defaults.ai_context_limit),
    }

    all_settings = {**critical_settings, **other_settings}

    # Belt and braces: never create a key the model config owns.
    all_settings = {
        key: value
        for key, value in all_settings.items()
        if key not in MODEL_CONFIG_KEYS
    }

    created_settings = {}

    for key, default_value in all_settings.items():
        existing = db.query(SettingsModel).filter(SettingsModel.key == key).first()
        if not existing:
            db.add(SettingsModel(key=key, value=str(default_value)))
            created_settings[key] = default_value

    if created_settings:
        db.commit()

    return created_settings


# Keys owned by config/models.json. initialize_default_settings() must never
# create them, otherwise the config file stops being effective.
MODEL_CONFIG_KEYS = frozenset(
    {
        'ai_provider',
        'chat_model',
        'analysis_model',
        'vision_model',
        'embedding_provider',
        'local_embedding_model',
        'embedding_model',
        'ocr_engine',
        'vision_ocr_enabled',
        'vision_max_pages',
        'vision_max_image_bytes',
        'pdf_text_layer_first',
        'reasoning_effort',
        'groq_base_url',
        'ai_temperature_extraction',
        'ai_temperature_chat',
        'ai_max_tokens_extraction',
        'ai_max_tokens_chat',
        'ai_max_tokens_vision',
    }
)


def ensure_critical_settings(db: Session) -> bool:
    """
    Ensure all critical settings exist in the database.
    Returns True if all critical settings exist, False otherwise.
    """
    critical_keys = ['staging_folder', 'data_folder', 'storage_folder']
    
    for key in critical_keys:
        setting = db.query(SettingsModel).filter(SettingsModel.key == key).first()
        if not setting:
            return False
    
    return True