"""Regressions for behaviour discovered against the live Groq API.

1. Reasoning tokens are billed against ``max_completion_tokens``. A budget of
   16 returned an empty message with ``finish_reason='length'``.
2. ``qwen/qwen3.6-27b`` is a hybrid reasoning model that emits its chain of
   thought inline as ``<think>...</think>`` unless reasoning is disabled. That
   text must never reach the OCR index or a user-facing answer.
3. Groq counts ``prompt + max_tokens`` against the per-minute token limit, and
   the vision model's free tier is 8000 TPM, so the vision budget must be small.
"""
from types import SimpleNamespace

import pytest
from PIL import Image

from app.config import Settings
from app.services.ai_service import MIN_REASONING_COMPLETION_TOKENS, AIService
from app.services.sdk_compat import strip_reasoning_blocks
from app.services.vision_ocr import VisionOCR


def _reply(content, finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content), finish_reason=finish_reason
            )
        ]
    )


class FakeClient:
    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self._responses:
            result = self._responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return _reply("ok")


# ---------------------------------------------------------------------------
# 1. Reasoning token budget
# ---------------------------------------------------------------------------
def test_small_budget_is_raised_to_the_reasoning_floor(groq_settings):
    """A 16-token budget produced an empty response against the real API."""
    client = FakeClient()
    service = AIService(settings=groq_settings, client=client)

    service.chat_completion(messages=[{"role": "user", "content": "hi"}], max_tokens=16)

    assert client.calls[0]["max_completion_tokens"] == MIN_REASONING_COMPLETION_TOKENS


def test_large_budget_is_left_alone(groq_settings):
    client = FakeClient()
    service = AIService(settings=groq_settings, client=client)

    service.chat_completion(messages=[{"role": "user", "content": "hi"}], max_tokens=4096)

    assert client.calls[0]["max_completion_tokens"] == 4096


def test_non_reasoning_provider_keeps_the_small_budget():
    settings = Settings(ai_provider="openai", openai_api_key="sk-x")
    client = FakeClient()
    service = AIService(settings=settings, client=client)

    service.chat_completion(messages=[{"role": "user", "content": "hi"}], max_tokens=16)

    assert client.calls[0]["max_tokens"] == 16


def test_truncated_empty_response_is_retried_with_more_room(groq_settings):
    client = FakeClient([_reply("", finish_reason="length"), _reply("ok")])
    service = AIService(settings=groq_settings, client=client)

    response = service.chat_completion(
        messages=[{"role": "user", "content": "hi"}], max_tokens=512
    )

    assert response.choices[0].message.content == "ok"
    assert len(client.calls) == 2
    assert client.calls[1]["max_completion_tokens"] > client.calls[0]["max_completion_tokens"]


def test_truncation_retry_happens_at_most_once(groq_settings):
    client = FakeClient(
        [_reply("", finish_reason="length"), _reply("", finish_reason="length")]
    )
    service = AIService(settings=groq_settings, client=client)

    service.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert len(client.calls) == 2


def test_non_empty_truncated_response_is_not_retried(groq_settings):
    """Partial content is still useful; only a *blank* response warrants a retry."""
    client = FakeClient([_reply("partial answer", finish_reason="length")])
    service = AIService(settings=groq_settings, client=client)

    response = service.chat_completion(messages=[{"role": "user", "content": "hi"}])

    assert response.choices[0].message.content == "partial answer"
    assert len(client.calls) == 1


# ---------------------------------------------------------------------------
# 2. Inline <think> blocks
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("<think>reasoning here</think>Actual text", "Actual text"),
        ("\n<think>\nmulti\nline\n</think>\nInvoice 42", "Invoice 42"),
        ("<THINK>upper</THINK>Text", "Text"),
        ("No reasoning at all", "No reasoning at all"),
        ("Text before <think>mid</think> after", "Text before  after"),
        ("<think>unterminated block runs to the end", ""),
        ("", ""),
    ],
)
def test_strip_reasoning_blocks(raw, expected):
    assert strip_reasoning_blocks(raw) == expected


def test_vision_disables_reasoning_for_groq(groq_settings):
    """Reasoning pollutes transcription and wastes the tight vision budget."""
    client = FakeClient([_reply("Invoice")])
    vision = VisionOCR(groq_settings, client=client)

    vision.transcribe_image(Image.new("RGB", (200, 100), "white"))

    sent = dict(client.calls[0])
    sent.update(sent.pop("extra_body", {}) or {})
    assert sent["reasoning_effort"] == "none"


def test_vision_strips_think_blocks_from_transcription(groq_settings):
    client = FakeClient(
        [_reply("<think>\nThe user wants the text.\n</think>\nStadtwerke Musterstadt")]
    )
    vision = VisionOCR(groq_settings, client=client)

    text = vision.transcribe_image(Image.new("RGB", (200, 100), "white"))

    assert text == "Stadtwerke Musterstadt"
    assert "<think>" not in text


def test_rag_answer_strips_think_blocks(groq_settings, tmp_path):
    settings = groq_settings.model_copy(update={"logs_folder": str(tmp_path)})
    client = FakeClient([_reply("<think>plan</think>\n## Antwort\n140,90 EUR ([Doc1])")])
    service = AIService(settings=settings, client=client)

    answer = service.answer_question("Amount?", ["ctx"], ["T"], ["id"])

    assert "<think>" not in answer
    assert answer.startswith("## Antwort")


def test_metadata_json_survives_a_think_prefix(groq_settings):
    import json

    payload = {
        "title": "2025-01-01_rechnung_X_a_b_c",
        "document_type": "rechnung",
        "date": "2025-01-01",
        "sender": "X",
        "tax_relevant": False,
        "tags": ["a", "b"],
        "summary": "s",
    }
    client = FakeClient([_reply(f"<think>deciding</think>{json.dumps(payload)}")])
    service = AIService(settings=groq_settings, client=client)

    result = service.extract_document_metadata("text", "f.pdf")

    assert result.doctype_name == "rechnung"


# ---------------------------------------------------------------------------
# 3. Vision token budget must stay under the free-tier TPM limit
# ---------------------------------------------------------------------------
def test_vision_token_budget_fits_the_free_tier():
    """8192 made every vision request fail with HTTP 413 (TPM limit 8000)."""
    settings = Settings(ai_provider="groq", groq_api_key="gsk_x")

    assert settings.ai_max_tokens_vision <= 4096, (
        "max_tokens_vision counts against the vision model's 8000 TPM budget "
        "together with the prompt; keep it small"
    )


def test_shipped_config_keeps_the_vision_budget_small():
    from app.services.model_config import load_model_config

    generation = load_model_config(force=True)["generation"]

    assert generation["max_tokens_vision"] <= 4096
