"""AI Client Factory for creating Groq, OpenAI or Azure OpenAI clients.

Groq exposes an OpenAI-compatible REST API, so it reuses the ``openai`` SDK
with a custom ``base_url``. Note that Groq does **not** provide an embeddings
endpoint - embeddings are handled separately by
:mod:`app.services.embedding_service`.
"""
from openai import OpenAI, AzureOpenAI
from typing import Union
from loguru import logger
from sqlalchemy.orm import Session
import httpx
from ..config import get_settings
from .model_config import provider_spec

GROQ_DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"


def _build_http_client(settings) -> httpx.Client:
    """Shared httpx client with explicit timeouts and connection limits."""
    return httpx.Client(
        timeout=httpx.Timeout(
            connect=10.0,
            read=settings.ai_request_timeout,
            write=30.0,  # vision requests upload base64 images
            pool=5.0,
        ),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=5),
    )


class AIClientFactory:
    """Factory class for creating AI clients based on provider configuration"""

    @staticmethod
    def groq_keys(db: Session = None) -> list[str]:
        """
        The Groq keys to try, in order, with blanks and duplicates removed.

        Two accounts on a free tier are two separate quotas. Listing them here
        rather than in the caller means "how many keys are there" is answered
        once, and adding a third later is one line.
        """
        settings = get_settings(db)
        keys = [settings.groq_api_key, settings.groq_api_key_2]
        seen, out = set(), []
        for k in keys:
            k = (k or "").strip()
            if k and k not in seen:
                seen.add(k)
                out.append(k)
        return out

    @staticmethod
    def create_client(db: Session = None, key_index: int = 0) -> Union[OpenAI, AzureOpenAI]:
        """
        Create the client for the configured provider.

        `key_index` selects which Groq key to use. It exists so AIService can
        fall back to the second account when the first is out of quota; every
        other caller leaves it alone and gets the primary key.
        """
        settings = get_settings(db)
        provider = (settings.ai_provider or "").lower()

        if provider == "groq":
            keys = AIClientFactory.groq_keys(db)
            if not keys:
                raise ValueError(
                    "Groq API key must be configured. Set GROQ_API_KEY in .env "
                    "or save it under Settings -> AI Configuration."
                )
            if key_index >= len(keys):
                raise IndexError(f"No Groq key at position {key_index + 1}")

            base_url = settings.groq_base_url or GROQ_DEFAULT_BASE_URL
            logger.info(
                f"Creating Groq client on key {key_index + 1} of {len(keys)} "
                f"with base_url: {base_url}"
            )

            return OpenAI(
                api_key=keys[key_index],
                base_url=base_url,
                http_client=_build_http_client(settings),
                max_retries=0,  # retries are handled by AIService
            )

        if provider == "azure":
            if not settings.azure_openai_api_key or not settings.azure_openai_endpoint:
                raise ValueError("Azure OpenAI API key and endpoint must be configured")

            logger.info(
                f"Creating Azure OpenAI client with endpoint: {settings.azure_openai_endpoint}"
            )

            return AzureOpenAI(
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                azure_endpoint=settings.azure_openai_endpoint,
                http_client=_build_http_client(settings),
                max_retries=0,
            )

        # Standard OpenAI client
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key must be configured")

        logger.info("Creating standard OpenAI client")

        return OpenAI(
            api_key=settings.openai_api_key,
            http_client=_build_http_client(settings),
            max_retries=0,
        )

    @staticmethod
    def get_chat_model(settings) -> str:
        """Get the appropriate chat model name based on provider"""
        if (settings.ai_provider or "").lower() == "azure":
            return settings.azure_openai_chat_deployment or settings.chat_model
        return settings.chat_model

    @staticmethod
    def get_analysis_model(settings) -> str:
        """Get the appropriate analysis/extraction model name based on provider"""
        if (settings.ai_provider or "").lower() == "azure":
            return settings.azure_openai_chat_deployment or settings.analysis_model
        return settings.analysis_model

    @staticmethod
    def get_vision_model(settings) -> str:
        """Get the appropriate vision model name based on provider"""
        if (settings.ai_provider or "").lower() == "azure":
            # Azure serves vision through a deployment name too; fall back to
            # the chat deployment when no dedicated vision deployment exists.
            return settings.vision_model or settings.azure_openai_chat_deployment
        return settings.vision_model

    @staticmethod
    def get_embeddings_model(settings) -> str:
        """Get the appropriate embeddings model name based on provider"""
        provider = (settings.embedding_provider or "local").lower()
        if provider == "local":
            return settings.local_embedding_model
        if provider == "azure":
            return settings.azure_openai_embeddings_deployment or settings.embedding_model
        return settings.embedding_model

    @staticmethod
    def get_capabilities(settings) -> dict:
        """Return the capability flags for the active provider."""
        return provider_spec((settings.ai_provider or "").lower())

    @staticmethod
    def validate_configuration(settings) -> dict:
        """Validate the AI configuration and return status"""
        errors = []
        warnings = []
        provider = (settings.ai_provider or "").lower()

        if provider == "groq":
            if not settings.groq_api_key:
                errors.append("Groq API key is missing (set GROQ_API_KEY)")
            if not settings.groq_base_url:
                warnings.append("Groq base URL is empty; the default will be used")
            if not settings.chat_model:
                errors.append("Groq chat model is not configured")
            if not settings.vision_model:
                warnings.append(
                    "No vision model configured; scanned documents fall back to Tesseract"
                )
        elif provider == "azure":
            if not settings.azure_openai_api_key:
                errors.append("Azure OpenAI API key is missing")
            if not settings.azure_openai_endpoint:
                errors.append("Azure OpenAI endpoint is missing")
            if not settings.azure_openai_chat_deployment:
                warnings.append("Azure OpenAI chat deployment name is missing")
            if (
                settings.embedding_provider or "local"
            ).lower() == "azure" and not settings.azure_openai_embeddings_deployment:
                warnings.append("Azure OpenAI embeddings deployment name is missing")
        elif provider == "openai":
            if not settings.openai_api_key:
                errors.append("OpenAI API key is missing")
        else:
            errors.append(f"Unknown AI provider: {settings.ai_provider}")

        # Embeddings are configured independently of the chat provider.
        embedding_provider = (settings.embedding_provider or "local").lower()
        if embedding_provider == "openai" and not settings.openai_api_key:
            errors.append(
                "Embedding provider is 'openai' but no OpenAI API key is configured"
            )
        elif embedding_provider == "azure" and not settings.azure_openai_api_key:
            errors.append(
                "Embedding provider is 'azure' but no Azure OpenAI API key is configured"
            )

        return {
            "provider": settings.ai_provider,
            "embedding_provider": embedding_provider,
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }
