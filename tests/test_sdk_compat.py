"""Guards against sending keyword arguments the installed openai SDK rejects.

The SDK has an explicit signature and no ``**kwargs``, so a parameter it
predates raises TypeError locally, before any HTTP request. Fake clients in the
other test modules accept anything, so these tests deliberately check against
the *real* SDK.
"""
import inspect

import pytest
from openai.resources.chat.completions import Completions

from app.config import Settings
from app.services.ai_service import AIService
from app.services.sdk_compat import adapt_params, supported_params
from app.services.vision_ocr import VisionOCR


SDK_SIGNATURE = inspect.signature(Completions.create)
SDK_PARAMS = set(SDK_SIGNATURE.parameters)


class RealSignatureClient:
    """A double whose create() mirrors the installed SDK's signature exactly.

    ``__signature__`` is set so ``inspect.signature`` reports the real SDK
    parameters, and the body rejects anything outside them exactly like the
    SDK's own keyword validation would.
    """

    def __init__(self):
        self.received = None
        outer = self

        class Completions_:
            def create(self, **kwargs):
                unexpected = set(kwargs) - SDK_PARAMS
                if unexpected:
                    raise TypeError(
                        f"create() got an unexpected keyword argument {sorted(unexpected)!r}"
                    )
                outer.received = kwargs
                from types import SimpleNamespace

                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
                )

        # Make introspection see the genuine SDK signature.
        Completions_.create.__signature__ = SDK_SIGNATURE

        from types import SimpleNamespace

        self.chat = SimpleNamespace(completions=Completions_())


def test_supported_params_detects_the_real_sdk():
    allowed = supported_params(RealSignatureClient())

    assert allowed is not None
    assert "model" in allowed
    assert "messages" in allowed
    assert "extra_body" in allowed


def test_supported_params_returns_none_for_kwargs_doubles():
    from types import SimpleNamespace

    class Anything:
        def create(self, **kwargs):
            return None

    client = SimpleNamespace(chat=SimpleNamespace(completions=Anything()))
    assert supported_params(client) is None


def test_unknown_params_are_moved_into_extra_body():
    client = RealSignatureClient()

    adapted = adapt_params(
        client,
        {"model": "m", "messages": [], "definitely_not_a_real_param": 1},
    )

    assert "definitely_not_a_real_param" not in adapted
    assert adapted["extra_body"]["definitely_not_a_real_param"] == 1


def test_adapt_params_merges_with_existing_extra_body():
    client = RealSignatureClient()

    adapted = adapt_params(
        client,
        {"model": "m", "extra_body": {"a": 1}, "made_up_param": 2},
    )

    assert adapted["extra_body"] == {"a": 1, "made_up_param": 2}


def test_adapt_params_is_a_noop_for_kwargs_doubles():
    from types import SimpleNamespace

    class Anything:
        def create(self, **kwargs):
            return None

    client = SimpleNamespace(chat=SimpleNamespace(completions=Anything()))
    params = {"model": "m", "reasoning_effort": "high"}

    assert adapt_params(client, params) == params


# ---------------------------------------------------------------------------
# The real payloads the application sends
# ---------------------------------------------------------------------------
def test_groq_chat_request_is_accepted_by_the_installed_sdk():
    """Regression: reasoning_effort/max_completion_tokens broke on SDK 1.3.7."""
    settings = Settings(
        ai_provider="groq", groq_api_key="gsk_x", reasoning_effort="high"
    )
    client = RealSignatureClient()
    service = AIService(settings=settings, client=client)

    service.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=2048,
        temperature=0.2,
        reasoning=True,
    )

    assert client.received is not None
    # Either sent natively or tunnelled through extra_body - never dropped.
    sent = dict(client.received)
    sent.update(sent.pop("extra_body", {}) or {})
    assert sent["max_completion_tokens"] == 2048
    assert sent["reasoning_effort"] == "high"


def test_metadata_extraction_request_is_accepted_by_the_installed_sdk():
    import json

    settings = Settings(ai_provider="groq", groq_api_key="gsk_x")
    client = RealSignatureClient()

    payload = {
        "title": "2025-01-01_rechnung_X_a_b_c",
        "document_type": "rechnung",
        "date": "2025-01-01",
        "sender": "X",
        "tax_relevant": False,
        "tags": ["a", "b"],
        "summary": "s",
    }

    original_create = client.chat.completions.create

    def create(**kwargs):
        original_create(**kwargs)
        from types import SimpleNamespace

        return SimpleNamespace(
            choices=[
                SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))
            ]
        )

    client.chat.completions.create = create

    service = AIService(settings=settings, client=client)
    result = service.extract_document_metadata("Rechnungstext", "r.pdf")

    assert result.doctype_name == "rechnung"
    assert client.received is not None


def test_vision_request_is_accepted_by_the_installed_sdk():
    from PIL import Image

    settings = Settings(ai_provider="groq", groq_api_key="gsk_x")
    client = RealSignatureClient()
    vision = VisionOCR(settings, client=client)

    vision.transcribe_image(Image.new("RGB", (200, 100), "white"))

    sent = dict(client.received)
    sent.update(sent.pop("extra_body", {}) or {})
    assert sent["model"] == "qwen/qwen3.6-27b"
    assert sent["max_completion_tokens"] > 0
    assert sent["messages"][0]["content"][1]["type"] == "image_url"


@pytest.mark.parametrize("provider", ["groq", "openai", "azure"])
def test_every_provider_produces_an_sdk_compatible_request(provider):
    settings = Settings(
        ai_provider=provider,
        groq_api_key="gsk_x",
        openai_api_key="sk-x",
        azure_openai_api_key="k",
        azure_openai_endpoint="https://example.openai.azure.com",
        azure_openai_chat_deployment="dep",
    )
    client = RealSignatureClient()
    service = AIService(settings=settings, client=client)

    # Must not raise TypeError.
    service.chat_completion(
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=32,
        temperature=0.1,
        reasoning=True,
        response_format={"type": "json_object"},
    )

    assert client.received is not None
