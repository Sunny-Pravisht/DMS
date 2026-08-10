"""Pluggable embedding backend.

Groq's API is OpenAI-compatible for chat and vision but it does **not** expose
an ``/embeddings`` endpoint. Semantic search therefore needs its own backend,
selected via the ``embedding_provider`` setting:

``local``  (default)
    Runs ``all-MiniLM-L6-v2`` on the CPU through the ONNX runtime that ChromaDB
    already depends on. No API key, no extra pip dependency. The ~80 MB model is
    downloaded once on first use and cached under ``~/.cache/chroma``.

``openai`` / ``azure``
    Uses the corresponding hosted embeddings API. Requires a key for that
    provider even when chat runs on Groq.

Vector dimensions differ per backend (MiniLM = 384, text-embedding-3-small =
1536). Switching backends invalidates the existing Chroma collection, so run
``python cli.py reindex-vectors --force`` afterwards.
"""
import threading
from typing import List, Optional

from loguru import logger

# Nominal dimensions, used for the mismatch guard and diagnostics.
KNOWN_DIMENSIONS = {
    "all-minilm-l6-v2": 384,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class EmbeddingError(RuntimeError):
    """Raised when embeddings cannot be produced."""


class _LocalEmbedder:
    """Lazy wrapper around ChromaDB's bundled ONNX MiniLM model."""

    _instance: Optional["_LocalEmbedder"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._fn = None
        self._init_error: Optional[str] = None
        self._init_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "_LocalEmbedder":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _ensure_loaded(self):
        if self._fn is not None:
            return
        with self._init_lock:
            if self._fn is not None:
                return
            if self._init_error is not None:
                raise EmbeddingError(self._init_error)
            try:
                from chromadb.utils import embedding_functions

                # Name differs slightly across ChromaDB releases.
                factory = getattr(
                    embedding_functions, "ONNXMiniLM_L6_V2", None
                ) or getattr(
                    embedding_functions, "DefaultEmbeddingFunction", None
                )
                if factory is None:
                    raise ImportError(
                        "ChromaDB does not expose a default ONNX embedding function"
                    )
                logger.info(
                    "Initialising local ONNX embedding model (all-MiniLM-L6-v2). "
                    "The model is downloaded once on first use."
                )
                self._fn = factory()
                # Force the model download/warm-up now so the first document
                # upload does not pay the cost mid-pipeline.
                self._fn(["warmup"])
                logger.info("Local embedding model ready")
            except Exception as exc:
                self._init_error = (
                    f"Local embedding model unavailable: {exc}. "
                    "First use needs network access to download the ONNX model, "
                    "or switch embeddings.provider to 'openai' in config/models.json."
                )
                logger.error(self._init_error)
                raise EmbeddingError(self._init_error) from exc

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._ensure_loaded()
        result = self._fn(texts)
        # ChromaDB may return numpy arrays; normalise to plain lists of floats.
        return [[float(v) for v in vector] for vector in result]

    @property
    def available(self) -> bool:
        try:
            self._ensure_loaded()
            return True
        except EmbeddingError:
            return False


class EmbeddingService:
    """Produces embedding vectors using the configured backend."""

    def __init__(self, settings, client=None):
        """
        Args:
            settings: resolved application settings
            client: an OpenAI/AzureOpenAI client, only needed for hosted backends
        """
        self.settings = settings
        self.client = client
        self.provider = (getattr(settings, "embedding_provider", "local") or "local").lower()

    @property
    def model_name(self) -> str:
        if self.provider == "local":
            return self.settings.local_embedding_model
        if self.provider == "azure":
            return (
                self.settings.azure_openai_embeddings_deployment
                or self.settings.embedding_model
            )
        return self.settings.embedding_model

    @property
    def dimensions(self) -> Optional[int]:
        return KNOWN_DIMENSIONS.get(self.model_name.lower())

    def _hosted_client(self):
        """Build a client for the embedding provider when it differs from chat."""
        if self.client is not None and self.provider == (
            self.settings.ai_provider or ""
        ).lower():
            return self.client

        from openai import AzureOpenAI, OpenAI

        if self.provider == "azure":
            if not self.settings.azure_openai_api_key or not self.settings.azure_openai_endpoint:
                raise EmbeddingError(
                    "Azure embeddings selected but Azure key/endpoint are not configured"
                )
            return AzureOpenAI(
                api_key=self.settings.azure_openai_api_key,
                api_version=self.settings.azure_openai_api_version,
                azure_endpoint=self.settings.azure_openai_endpoint,
            )

        if not self.settings.openai_api_key:
            raise EmbeddingError(
                "OpenAI embeddings selected but OPENAI_API_KEY is not configured. "
                "Set embeddings.provider to 'local' in config/models.json to run "
                "embeddings on the CPU instead."
            )
        return OpenAI(api_key=self.settings.openai_api_key)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of texts."""
        if not texts:
            return []

        # Guard against absurd payloads; hosted APIs reject them anyway.
        trimmed = [(t or "")[:8000] for t in texts]

        if self.provider == "local":
            return _LocalEmbedder.instance().embed(trimmed)

        client = self._hosted_client()
        response = client.embeddings.create(model=self.model_name, input=trimmed)
        # Preserve request order (the API guarantees `index`, but be explicit).
        ordered = sorted(response.data, key=lambda item: item.index)
        return [[float(v) for v in item.embedding] for item in ordered]

    def embed_query(self, text: str) -> List[float]:
        """Embed a single text and return its vector."""
        vectors = self.embed_documents([text])
        if not vectors:
            raise EmbeddingError("Embedding backend returned no vectors")
        return vectors[0]

    def describe(self) -> dict:
        """Diagnostics for the health endpoint."""
        info = {
            "provider": self.provider,
            "model": self.model_name,
            "dimensions": self.dimensions,
        }
        if self.provider == "local":
            info["ready"] = _LocalEmbedder.instance().available
        else:
            info["ready"] = bool(
                self.settings.azure_openai_api_key
                if self.provider == "azure"
                else self.settings.openai_api_key
            )
        return info


def warmup_local_model() -> bool:
    """Preload the local ONNX model. Returns True when it is usable."""
    return _LocalEmbedder.instance().available
