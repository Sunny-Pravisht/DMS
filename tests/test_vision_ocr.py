"""Tests for vision-model transcription and the OCR engine chain."""
import base64
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from app.config import Settings
from app.services import ocr_service as ocr_module
from app.services.ocr_service import OCRService
from app.services.vision_ocr import VisionOCR, VisionOCRError


class FakeCompletions:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        result = self._responses.pop(0) if self._responses else _reply("text")
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    def __init__(self, responses=None):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses or []))

    @property
    def calls(self):
        return self.chat.completions.calls


def _reply(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def make_image(width=800, height=400, text="RECHNUNG 2025"):
    image = Image.new("RGB", (width, height), "white")
    ImageDraw.Draw(image).text((20, 20), text, fill="black")
    return image


# ---------------------------------------------------------------------------
# Image encoding
# ---------------------------------------------------------------------------
def test_encode_image_produces_jpeg_data_uri(groq_settings):
    vision = VisionOCR(groq_settings, client=FakeClient())

    uri = vision.encode_image(make_image())

    assert uri.startswith("data:image/jpeg;base64,")
    payload = uri.split(",", 1)[1]
    assert base64.b64decode(payload)[:2] == b"\xff\xd8"  # JPEG SOI marker


def test_encode_image_flattens_transparency(groq_settings):
    vision = VisionOCR(groq_settings, client=FakeClient())
    rgba = Image.new("RGBA", (100, 100), (255, 0, 0, 128))

    uri = vision.encode_image(rgba)

    assert uri.startswith("data:image/jpeg;base64,")


def test_encode_image_downscales_oversized_images(groq_settings):
    vision = VisionOCR(groq_settings, client=FakeClient())
    huge = make_image(width=6000, height=4000)

    uri = vision.encode_image(huge)
    raw = base64.b64decode(uri.split(",", 1)[1])

    assert len(raw) * 4 / 3 <= vision.max_bytes


def test_encode_image_respects_a_tight_byte_budget():
    settings = Settings(
        ai_provider="groq", groq_api_key="gsk_x", vision_max_image_bytes=80 * 1024
    )
    vision = VisionOCR(settings, client=FakeClient())

    uri = vision.encode_image(make_image(width=4000, height=3000))
    raw = base64.b64decode(uri.split(",", 1)[1])

    assert len(raw) * 4 / 3 <= 80 * 1024


# ---------------------------------------------------------------------------
# Transcription
# ---------------------------------------------------------------------------
def test_transcribe_sends_image_url_content_block(groq_settings):
    client = FakeClient([_reply("Invoice No. 42")])
    vision = VisionOCR(groq_settings, client=client)

    text = vision.transcribe_image(make_image())

    assert text == "Invoice No. 42"
    sent = client.calls[0]
    assert sent["model"] == "qwen/qwen3.6-27b"
    content = sent["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    # Groq uses max_completion_tokens and deterministic transcription.
    assert sent["max_completion_tokens"] > 0
    assert sent["temperature"] == 0.0


def test_transcribe_strips_markdown_fences(groq_settings):
    client = FakeClient([_reply("```\nInvoice\nAmount 10 EUR\n```")])
    vision = VisionOCR(groq_settings, client=client)

    assert vision.transcribe_image(make_image()) == "Invoice\nAmount 10 EUR"


def test_transcribe_returns_empty_for_no_text_sentinel(groq_settings):
    client = FakeClient([_reply("[NO_TEXT_FOUND]")])
    vision = VisionOCR(groq_settings, client=client)

    assert vision.transcribe_image(make_image()) == ""


def test_transcribe_raises_on_api_failure(groq_settings):
    client = FakeClient([RuntimeError("boom")])
    vision = VisionOCR(groq_settings, client=client)

    with pytest.raises(VisionOCRError, match="qwen/qwen3.6-27b"):
        vision.transcribe_image(make_image())


def test_transcribe_pages_joins_pages(groq_settings):
    client = FakeClient([_reply("page one"), _reply("page two")])
    vision = VisionOCR(groq_settings, client=client)

    text = vision.transcribe_pages([make_image(), make_image()], source_name="doc.pdf")

    assert text == "page one\n\npage two"
    assert len(client.calls) == 2


def test_transcribe_pages_honours_the_page_limit():
    settings = Settings(
        ai_provider="groq", groq_api_key="gsk_x", vision_max_pages=2
    )
    client = FakeClient([_reply("a"), _reply("b"), _reply("c")])
    vision = VisionOCR(settings, client=client)

    text = vision.transcribe_pages([make_image()] * 5, source_name="doc.pdf")

    assert len(client.calls) == 2
    assert "3 further page(s) not transcribed" in text


def test_transcribe_pages_survives_one_bad_page(groq_settings):
    client = FakeClient([_reply("good"), RuntimeError("bad page"), _reply("also good")])
    vision = VisionOCR(groq_settings, client=client)

    text = vision.transcribe_pages([make_image()] * 3, source_name="doc.pdf")

    assert "good" in text
    assert "also good" in text
    # The gap must be visible, not silently dropped.
    assert "Page 2 of 3 could not be transcribed" in text


def test_rate_limited_page_is_retried_rather_than_dropped(groq_settings, monkeypatch):
    """A 429 mid-document used to silently lose the page."""
    import app.services.vision_ocr as vision_module

    slept = []
    monkeypatch.setattr(vision_module.time, "sleep", lambda s: slept.append(s))

    rate_limit = RuntimeError(
        "Error code: 429 - rate_limit_exceeded on tokens per minute (TPM): "
        "Limit 8000, Used 6305, Requested 4600. Please try again in 21.7875s."
    )
    client = FakeClient([rate_limit, _reply("page recovered")])
    vision = VisionOCR(groq_settings, client=client)

    text = vision.transcribe_image(make_image())

    assert text == "page recovered"
    assert len(client.calls) == 2
    # Honoured the delay the API asked for.
    assert slept and 21.0 < slept[0] < 25.0


def test_rate_limit_retries_are_bounded(groq_settings, monkeypatch):
    import app.services.vision_ocr as vision_module

    monkeypatch.setattr(vision_module.time, "sleep", lambda s: None)

    rate_limit = RuntimeError("Error code: 429 - rate_limit_exceeded, try again in 1s")
    client = FakeClient([rate_limit] * 10)
    vision = VisionOCR(groq_settings, client=client)

    with pytest.raises(VisionOCRError, match="rate limited"):
        vision.transcribe_image(make_image())

    assert len(client.calls) == vision_module.MAX_RATE_LIMIT_RETRIES + 1


def test_non_rate_limit_errors_are_not_retried(groq_settings, monkeypatch):
    import app.services.vision_ocr as vision_module

    monkeypatch.setattr(vision_module.time, "sleep", lambda s: None)

    client = FakeClient([RuntimeError("500 internal error")] * 5)
    vision = VisionOCR(groq_settings, client=client)

    with pytest.raises(VisionOCRError):
        vision.transcribe_image(make_image())

    assert len(client.calls) == 1


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Please try again in 21.7875s.", 21.7875),
        ("please try again in 3s", 3.0),
        ("no delay mentioned", None),
    ],
)
def test_retry_delay_parsing(message, expected):
    from app.services.vision_ocr import _parse_retry_after

    assert _parse_retry_after(message) == expected


# ---------------------------------------------------------------------------
# OCR engine chain
# ---------------------------------------------------------------------------
def test_vision_disabled_without_api_key():
    settings = Settings(ai_provider="groq", groq_api_key=None, ocr_engine="auto")

    assert settings.vision_available is False
    assert OCRService(settings=settings).vision_enabled is False


def test_vision_disabled_when_engine_is_tesseract(groq_settings):
    settings = groq_settings.model_copy(update={"ocr_engine": "tesseract"})

    assert OCRService(settings=settings).vision_enabled is False


def test_vision_enabled_for_auto_engine_with_key(groq_settings):
    service = OCRService(settings=groq_settings, vision=object())

    assert service.engine == "auto"
    assert service.vision_enabled is True


def test_image_extraction_prefers_vision(groq_settings, tmp_path):
    image_path = tmp_path / "scan.png"
    make_image().save(image_path)

    class StubVision:
        def __init__(self):
            self.called_with = None

        def transcribe_path(self, path, hint=None):
            self.called_with = path
            return "vision text"

    stub = StubVision()
    service = OCRService(settings=groq_settings, vision=stub)

    assert service.extract_text(image_path) == "vision text"
    assert stub.called_with == image_path


def test_image_extraction_falls_back_to_tesseract(groq_settings, tmp_path, monkeypatch):
    image_path = tmp_path / "scan.png"
    make_image().save(image_path)

    class FailingVision:
        def transcribe_path(self, path, hint=None):
            raise VisionOCRError("model unavailable")

    service = OCRService(settings=groq_settings, vision=FailingVision())
    monkeypatch.setattr(service, "_tesseract_image", lambda p: "tesseract text")

    assert service.extract_text(image_path) == "tesseract text"


def test_image_extraction_reports_when_all_engines_fail(groq_settings, tmp_path, monkeypatch):
    image_path = tmp_path / "scan.png"
    make_image().save(image_path)

    class FailingVision:
        def transcribe_path(self, path, hint=None):
            raise VisionOCRError("vision down")

    service = OCRService(settings=groq_settings, vision=FailingVision())

    def failing_tesseract(_path):
        raise RuntimeError("tesseract missing")

    monkeypatch.setattr(service, "_tesseract_image", failing_tesseract)

    with pytest.raises(RuntimeError, match="All OCR engines failed"):
        service.extract_text(image_path)


def test_text_files_never_touch_ocr(groq_settings, tmp_path):
    path = tmp_path / "note.md"
    path.write_text("# Note\nContent", encoding="utf-8")

    class ExplodingVision:
        def transcribe_path(self, *_a, **_k):
            raise AssertionError("vision must not be called for text files")

    service = OCRService(settings=groq_settings, vision=ExplodingVision())

    assert service.extract_text(path) == "# Note\nContent"


def test_text_file_encoding_fallback(groq_settings, tmp_path):
    path = tmp_path / "latin.txt"
    # Non-UTF-8 bytes: the accented character is what forces the fallback.
    path.write_bytes("Café invoice 25 EUR".encode("cp1252"))

    text = OCRService(settings=groq_settings).extract_text(path)

    assert "invoice" in text and len(text) > 5


def test_unsupported_extension_raises(groq_settings, tmp_path):
    path = tmp_path / "archive.zip"
    path.write_bytes(b"PK\x03\x04")

    with pytest.raises(ValueError, match="Unsupported file type"):
        OCRService(settings=groq_settings).extract_text(path)


def test_missing_file_raises(groq_settings, tmp_path):
    with pytest.raises(FileNotFoundError):
        OCRService(settings=groq_settings).extract_text(tmp_path / "nope.pdf")


# ---------------------------------------------------------------------------
# PDF handling
# ---------------------------------------------------------------------------
def _digital_pdf(path, text):
    """Write a minimal PDF carrying a real text layer."""
    from PyPDF2 import PdfWriter

    try:
        from reportlab.pdfgen import canvas  # noqa: F401
    except ImportError:
        pytest.skip("reportlab not installed; cannot synthesise a text-layer PDF")

    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    c.drawString(72, 720, text)
    c.save()
    return path


def test_pdf_text_layer_is_used_before_ocr(groq_settings, tmp_path, monkeypatch):
    pdf_path = tmp_path / "digital.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    long_text = "Invoice number 12345 " * 20

    service = OCRService(settings=groq_settings, vision=object())
    monkeypatch.setattr(service, "extract_pdf_text_layer", lambda p: long_text)

    def must_not_render(*_a, **_k):
        raise AssertionError("should not rasterise a PDF with a good text layer")

    monkeypatch.setattr(service, "render_pdf_pages", must_not_render)

    assert service.extract_text_from_pdf(pdf_path) == long_text


def test_sparse_text_layer_falls_through_to_vision(groq_settings, tmp_path, monkeypatch):
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class StubVision:
        def transcribe_pages(self, pages, source_name=""):
            return "vision transcription"

    service = OCRService(settings=groq_settings, vision=StubVision())
    monkeypatch.setattr(service, "extract_pdf_text_layer", lambda p: "tiny")
    monkeypatch.setattr(service, "render_pdf_pages", lambda p, dpi=200: [make_image()])

    assert service.extract_text_from_pdf(pdf_path) == "vision transcription"


def test_pdf_falls_back_to_sparse_text_layer_when_render_fails(
    groq_settings, tmp_path, monkeypatch
):
    """No poppler + no OCR should still surface whatever text exists."""
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    service = OCRService(settings=groq_settings, vision=object())
    monkeypatch.setattr(service, "extract_pdf_text_layer", lambda p: "short text")

    def no_poppler(*_a, **_k):
        raise RuntimeError("poppler not installed")

    monkeypatch.setattr(service, "render_pdf_pages", no_poppler)

    assert service.extract_text_from_pdf(pdf_path) == "short text"


def test_pdf_raises_actionable_error_when_nothing_works(groq_settings, tmp_path, monkeypatch):
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    service = OCRService(settings=groq_settings, vision=object())
    monkeypatch.setattr(service, "extract_pdf_text_layer", lambda p: "")

    def no_poppler(*_a, **_k):
        raise RuntimeError("poppler not installed")

    monkeypatch.setattr(service, "render_pdf_pages", no_poppler)

    with pytest.raises(RuntimeError, match="poppler"):
        service.extract_text_from_pdf(pdf_path)


def test_engine_vision_skips_the_text_layer(groq_settings, tmp_path, monkeypatch):
    settings = groq_settings.model_copy(update={"ocr_engine": "vision"})
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    class StubVision:
        def transcribe_pages(self, pages, source_name=""):
            return "forced vision"

    service = OCRService(settings=settings, vision=StubVision())

    def must_not_read_text_layer(_p):
        raise AssertionError("engine=vision must not read the text layer")

    monkeypatch.setattr(service, "extract_pdf_text_layer", must_not_read_text_layer)
    monkeypatch.setattr(service, "render_pdf_pages", lambda p, dpi=200: [make_image()])

    assert service.extract_text_from_pdf(pdf_path) == "forced vision"


def test_describe_reports_engine_state(groq_settings):
    info = OCRService(settings=groq_settings).describe()

    assert info["engine"] == "auto"
    assert info["vision_model"] == "qwen/qwen3.6-27b"
    assert "tesseract_available" in info
    assert "pdf_text_layer_available" in info


def test_tesseract_detection_is_cached(monkeypatch, groq_settings):
    """Resolving the binary shells out; it must happen at most once."""
    ocr_module.reset_tesseract_cache()
    calls = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        raise FileNotFoundError

    monkeypatch.setattr(ocr_module.subprocess, "run", fake_run)

    OCRService(settings=groq_settings)
    first = len(calls)
    OCRService(settings=groq_settings)
    OCRService(settings=groq_settings)

    assert len(calls) == first
    ocr_module.reset_tesseract_cache()
