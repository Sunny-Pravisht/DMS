"""Tests for the Groq client factory, request shaping and JSON fallbacks."""
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.services import ai_service as ai_module
from app.services.ai_client_factory import AIClientFactory
from app.services.ai_service import AIService


class FakeCompletions:
    """Records requests and replays scripted responses/errors."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self._responses.pop(0) if self._responses else _reply("ok")
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    def __init__(self, responses=None):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses or []))

    @property
    def calls(self):
        return self.chat.completions.calls


def _reply(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


class BadRequest(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.status_code = 400


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------
def test_groq_client_uses_openai_sdk_with_groq_base_url(groq_settings, monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_client_factory.get_settings", lambda db=None: groq_settings
    )

    client = AIClientFactory.create_client()

    assert str(client.base_url).rstrip("/") == "https://api.groq.com/openai/v1"
    assert client.api_key == "gsk_test_key"


def test_groq_client_requires_api_key(monkeypatch):
    settings = Settings(ai_provider="groq", groq_api_key=None)
    monkeypatch.setattr(
        "app.services.ai_client_factory.get_settings", lambda db=None: settings
    )

    with pytest.raises(ValueError, match="Groq API key"):
        AIClientFactory.create_client()


def test_model_getters_for_groq(groq_settings):
    assert AIClientFactory.get_chat_model(groq_settings) == "openai/gpt-oss-120b"
    assert AIClientFactory.get_analysis_model(groq_settings) == "openai/gpt-oss-120b"
    assert AIClientFactory.get_vision_model(groq_settings) == "qwen/qwen3.6-27b"


def test_validate_configuration_flags_missing_groq_key():
    settings = Settings(ai_provider="groq", groq_api_key=None)
    result = AIClientFactory.validate_configuration(settings)

    assert result["valid"] is False
    assert any("Groq API key" in e for e in result["errors"])


def test_validate_configuration_passes_with_key(groq_settings):
    result = AIClientFactory.validate_configuration(groq_settings)

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["embedding_provider"] == "local"


def test_validate_configuration_rejects_openai_embeddings_without_key():
    settings = Settings(
        ai_provider="groq", groq_api_key="gsk_x", embedding_provider="openai", openai_api_key=None
    )
    result = AIClientFactory.validate_configuration(settings)

    assert result["valid"] is False
    assert any("openai" in e.lower() for e in result["errors"])


# ---------------------------------------------------------------------------
# Request shaping
# ---------------------------------------------------------------------------
def test_groq_request_uses_max_completion_tokens_and_reasoning(groq_settings):
    client = FakeClient([_reply("ok")])
    service = AIService(settings=groq_settings, client=client)

    # Above MIN_REASONING_COMPLETION_TOKENS so the floor does not apply here;
    # the floor itself is covered in test_reasoning_behaviour.py.
    service.chat_completion(
        messages=[{"role": "user", "content": "hi"}], max_tokens=1024, temperature=0.25
    )

    sent = client.calls[0]
    assert sent["model"] == "openai/gpt-oss-120b"
    assert sent["max_completion_tokens"] == 1024
    assert "max_tokens" not in sent
    assert sent["temperature"] == 0.25
    assert "reasoning_effort" not in sent  # reasoning=False by default


def test_reasoning_effort_is_sent_when_requested(groq_settings):
    client = FakeClient([_reply("ok")])
    service = AIService(settings=groq_settings, client=client)

    service.chat_completion(
        messages=[{"role": "user", "content": "hi"}], reasoning=True
    )

    assert client.calls[0]["reasoning_effort"] == "medium"


def test_reasoning_effort_none_disables_the_parameter():
    settings = Settings(
        ai_provider="groq", groq_api_key="gsk_x", reasoning_effort="none"
    )
    client = FakeClient([_reply("ok")])
    service = AIService(settings=settings, client=client)

    service.chat_completion(messages=[{"role": "user", "content": "hi"}], reasoning=True)

    assert "reasoning_effort" not in client.calls[0]


def test_openai_provider_uses_max_tokens():
    settings = Settings(
        ai_provider="openai", openai_api_key="sk-x", chat_model="gpt-4o-mini"
    )
    client = FakeClient([_reply("ok")])
    service = AIService(settings=settings, client=client)

    service.chat_completion(messages=[{"role": "user", "content": "hi"}], max_tokens=7)

    assert client.calls[0]["max_tokens"] == 7
    assert "max_completion_tokens" not in client.calls[0]


def test_azure_omits_temperature():
    settings = Settings(
        ai_provider="azure",
        azure_openai_api_key="k",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="dep",
    )
    client = FakeClient([_reply("ok")])
    service = AIService(settings=settings, client=client)

    service.chat_completion(messages=[{"role": "user", "content": "hi"}], temperature=0.5)

    assert "temperature" not in client.calls[0]


# ---------------------------------------------------------------------------
# Capability negotiation
# ---------------------------------------------------------------------------
def test_unsupported_reasoning_effort_is_dropped_and_retried(groq_settings):
    client = FakeClient(
        [BadRequest("400 unsupported parameter: 'reasoning_effort'"), _reply("ok")]
    )
    service = AIService(settings=groq_settings, client=client)

    response = service.chat_completion(
        messages=[{"role": "user", "content": "hi"}], reasoning=True
    )

    assert response.choices[0].message.content == "ok"
    assert "reasoning_effort" in client.calls[0]
    assert "reasoning_effort" not in client.calls[1]


def test_unsupported_response_format_falls_back(groq_settings):
    client = FakeClient(
        [BadRequest("400 invalid response_format json_schema"), _reply('{"a": 1}')]
    )
    service = AIService(settings=groq_settings, client=client)

    service.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        response_format={"type": "json_schema", "json_schema": {"name": "x", "schema": {}}},
    )

    assert "response_format" in client.calls[0]
    assert "response_format" not in client.calls[1]


def test_capability_cache_avoids_resending_a_rejected_parameter(groq_settings):
    client = FakeClient(
        [BadRequest("400 unsupported parameter: 'reasoning_effort'"), _reply("ok"), _reply("ok")]
    )
    service = AIService(settings=groq_settings, client=client)

    service.chat_completion(messages=[{"role": "user", "content": "a"}], reasoning=True)
    service.chat_completion(messages=[{"role": "user", "content": "b"}], reasoning=True)

    # Third call is the second chat_completion; it must not resend the param.
    assert "reasoning_effort" not in client.calls[2]


def test_non_parameter_errors_are_not_swallowed(groq_settings):
    class AuthError(Exception):
        status_code = 401

    settings = groq_settings.model_copy(update={"ai_max_retries": 0})
    client = FakeClient([AuthError("401 invalid api key")])
    service = AIService(settings=settings, client=client)

    with pytest.raises(Exception, match="401"):
        service.chat_completion(messages=[{"role": "user", "content": "hi"}])


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('```\n{"a": 1}\n```', {"a": 1}),
        ('Here you go:\n{"a": 1}\nHope that helps!', {"a": 1}),
        ('{"nested": {"b": [1, 2]}}', {"nested": {"b": [1, 2]}}),
    ],
)
def test_extract_json_handles_model_formatting(raw, expected):
    assert AIService._extract_json(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "no json at all"])
def test_extract_json_rejects_garbage(raw):
    with pytest.raises(ValueError):
        AIService._extract_json(raw)


# ---------------------------------------------------------------------------
# Metadata extraction
# ---------------------------------------------------------------------------
def test_extract_document_metadata_parses_groq_response(groq_settings):
    payload = {
        "title": "2025-01-15_rechnung_MustermannGmbH_Strom_Januar_2025",
        "document_type": "rechnung",
        "date": "2025-01-15",
        "sender": "MustermannGmbH",
        "tax_relevant": True,
        "tags": ["Strom", "Energie"],
        "summary": "Electricity invoice for January 2025.",
    }
    import json as _json

    client = FakeClient([_reply(_json.dumps(payload))])
    service = AIService(settings=groq_settings, client=client)

    result = service.extract_document_metadata("Invoice text", "invoice.pdf")

    assert result.title == payload["title"]
    assert result.doctype_name == "rechnung"
    assert result.correspondent_name == "MustermannGmbH"
    assert result.document_date == "2025-01-15"
    assert result.is_tax_relevant is True
    assert result.tag_names == ["Strom", "Energie"]

    # Structured outputs must have been requested for Groq.
    assert client.calls[0]["response_format"]["type"] == "json_schema"


def test_extract_document_metadata_repairs_a_bad_title(groq_settings):
    import json as _json

    payload = {
        "title": "Invoice",
        "document_type": "rechnung",
        "date": "2025-03-02",
        "sender": "ACME GmbH",
        "tax_relevant": False,
        "tags": ["a", "b"],
        "summary": "s",
    }
    client = FakeClient([_reply(_json.dumps(payload))])
    service = AIService(settings=groq_settings, client=client)

    result = service.extract_document_metadata("text", "f.pdf")

    assert result.title.startswith("2025-03-02_rechnung_AcmeGmbh")


def test_extract_document_metadata_without_schema_puts_schema_in_prompt():
    """When the model rejects json_schema the schema must move into the prompt."""
    import json as _json

    settings = Settings(ai_provider="groq", groq_api_key="gsk_x")
    payload = {
        "title": "2025-01-01_rechnung_X_a_b_c",
        "document_type": "rechnung",
        "date": "2025-01-01",
        "sender": "X",
        "tax_relevant": False,
        "tags": ["a", "b"],
        "summary": "s",
    }
    client = FakeClient(
        [BadRequest("400 response_format not supported"), _reply(_json.dumps(payload))]
    )
    service = AIService(settings=settings, client=client)

    result = service.extract_document_metadata("text", "f.pdf")
    assert result.doctype_name == "rechnung"

    # Second attempt: no response_format, and the retry succeeded.
    assert "response_format" not in client.calls[1]


def test_extract_document_metadata_tolerates_tags_as_string(groq_settings):
    import json as _json

    payload = {
        "title": "2025-01-01_rechnung_X_a_b_c",
        "document_type": "rechnung",
        "date": "2025-01-01",
        "sender": "X",
        "tax_relevant": False,
        "tags": "Strom, Energie",
        "summary": "s",
    }
    client = FakeClient([_reply(_json.dumps(payload))])
    service = AIService(settings=groq_settings, client=client)

    result = service.extract_document_metadata("text", "f.pdf")
    assert result.tag_names == ["Strom", "Energie"]


# ---------------------------------------------------------------------------
# RAG
# ---------------------------------------------------------------------------
def test_answer_question_builds_citations(groq_settings, tmp_path):
    settings = groq_settings.model_copy(update={"logs_folder": str(tmp_path)})
    client = FakeClient([_reply("## Answer\nSee [Doc1].")])
    service = AIService(settings=settings, client=client)

    answer = service.answer_question(
        question="How much is the invoice?",
        context_documents=["Rechnungsbetrag 100 EUR"],
        document_titles=["Invoice January"],
        document_ids=["doc-1"],
    )

    assert "[Doc1]" in answer
    prompt = client.calls[0]["messages"][-1]["content"]
    assert "Doc1 (Invoice January) - ID: doc-1" in prompt


def test_answer_question_rejects_empty_model_output(groq_settings, tmp_path):
    settings = groq_settings.model_copy(
        update={"logs_folder": str(tmp_path), "ai_max_retries": 0}
    )
    client = FakeClient([_reply("   ")])
    service = AIService(settings=settings, client=client)

    with pytest.raises(Exception):
        service.answer_question("q", ["ctx"])


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------
def test_ai_service_does_not_create_a_thread_pool_per_instance(groq_settings):
    """Regression: a per-instance executor leaked threads on every request."""
    services = [
        AIService(settings=groq_settings, client=FakeClient([_reply("ok")]))
        for _ in range(5)
    ]

    assert all(not hasattr(s, "executor") for s in services)
    assert ai_module._EXECUTOR is not None
