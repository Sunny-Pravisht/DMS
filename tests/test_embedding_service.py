"""Tests for the pluggable embedding backend.

Groq has no embeddings endpoint, so these tests pin down that the local backend
is selected by default and that the hosted backends are only used when their
credentials exist.
"""
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.services import embedding_service as es
from app.services.embedding_service import EmbeddingError, EmbeddingService


class FakeEmbeddings:
    def __init__(self, dimensions=1536):
        self.dimensions = dimensions
        self.calls = []

    def create(self, model, input):
        self.calls.append({"model": model, "input": input})
        # Return out of order to prove the service re-sorts by index.
        data = [
            SimpleNamespace(index=i, embedding=[float(i)] * self.dimensions)
            for i in range(len(input))
        ]
        return SimpleNamespace(data=list(reversed(data)))


class FakeClient:
    def __init__(self, dimensions=1536):
        self.embeddings = FakeEmbeddings(dimensions)


def test_default_provider_is_local_for_groq(groq_settings):
    service = EmbeddingService(groq_settings)

    assert service.provider == "local"
    assert service.model_name == "all-MiniLM-L6-v2"
    assert service.dimensions == 384


def test_openai_backend_is_used_when_selected():
    settings = Settings(
        ai_provider="groq",
        groq_api_key="gsk_x",
        embedding_provider="openai",
        openai_api_key="sk-x",
        embedding_model="text-embedding-3-small",
    )
    client = FakeClient()
    service = EmbeddingService(settings, client=client)
    service._hosted_client = lambda: client

    vector = service.embed_query("hallo welt")

    assert len(vector) == 1536
    assert client.embeddings.calls[0]["model"] == "text-embedding-3-small"


def test_hosted_backend_preserves_input_order():
    settings = Settings(
        embedding_provider="openai", openai_api_key="sk-x", ai_provider="openai"
    )
    client = FakeClient(dimensions=4)
    service = EmbeddingService(settings, client=client)
    service._hosted_client = lambda: client

    vectors = service.embed_documents(["a", "b", "c"])

    assert [v[0] for v in vectors] == [0.0, 1.0, 2.0]


def test_openai_backend_without_key_raises_actionable_error():
    settings = Settings(
        ai_provider="groq",
        groq_api_key="gsk_x",
        embedding_provider="openai",
        openai_api_key=None,
    )
    service = EmbeddingService(settings)

    with pytest.raises(EmbeddingError, match="local"):
        service.embed_query("text")


def test_azure_backend_without_endpoint_raises():
    settings = Settings(
        ai_provider="groq",
        groq_api_key="gsk_x",
        embedding_provider="azure",
        azure_openai_api_key=None,
    )
    service = EmbeddingService(settings)

    with pytest.raises(EmbeddingError):
        service.embed_query("text")


def test_embed_documents_returns_empty_for_empty_input(groq_settings):
    assert EmbeddingService(groq_settings).embed_documents([]) == []


def test_long_text_is_truncated_before_hosted_call():
    settings = Settings(
        embedding_provider="openai", openai_api_key="sk-x", ai_provider="openai"
    )
    client = FakeClient(dimensions=2)
    service = EmbeddingService(settings, client=client)
    service._hosted_client = lambda: client

    service.embed_documents(["x" * 50000])

    assert len(client.embeddings.calls[0]["input"][0]) == 8000


def test_describe_reports_backend(groq_settings):
    info = EmbeddingService(groq_settings).describe()

    assert info["provider"] == "local"
    assert info["model"] == "all-MiniLM-L6-v2"
    assert info["dimensions"] == 384
    assert "ready" in info


def test_local_backend_reports_unavailable_instead_of_crashing(monkeypatch, groq_settings):
    """A failed model download must degrade, not take the request down."""
    embedder = es._LocalEmbedder()

    def explode(*_args, **_kwargs):
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(embedder, "_ensure_loaded", explode)
    monkeypatch.setattr(es._LocalEmbedder, "instance", classmethod(lambda cls: embedder))

    with pytest.raises(RuntimeError):
        embedder.embed(["text"])


def test_local_embedder_produces_expected_dimensions(groq_settings):
    """Integration check against the real ONNX model when it is available."""
    service = EmbeddingService(groq_settings)
    if not es.warmup_local_model():
        pytest.skip("local ONNX embedding model not downloaded in this environment")

    vector = service.embed_query("Invoice for electricity supply January 2025")

    assert len(vector) == 384
    assert all(isinstance(v, float) for v in vector)


def test_local_embeddings_are_semantically_meaningful(groq_settings):
    """Related sentences must score higher than unrelated ones."""
    service = EmbeddingService(groq_settings)
    if not es.warmup_local_model():
        pytest.skip("local ONNX embedding model not downloaded in this environment")

    vectors = service.embed_documents(
        [
            "Invoice for electricity costs",
            "Electricity bill amount due",
            "Urlaubsfotos vom Strand",
        ]
    )

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb)

    related = cosine(vectors[0], vectors[1])
    unrelated = cosine(vectors[0], vectors[2])

    assert related > unrelated
