"""Vision-model based text extraction.

Sends page images to a multimodal model (Groq's Qwen vision model by default)
using the OpenAI-compatible ``image_url`` message format, and asks it to
transcribe the page verbatim.

This is used as an OCR engine alongside Tesseract. See
:class:`app.services.ocr_service.OCRService` for the selection logic.
"""
import base64
import io
import re
import time
from pathlib import Path
from typing import List, Optional

from loguru import logger
from PIL import Image

from .ai_client_factory import AIClientFactory
from .sdk_compat import adapt_params, strip_reasoning_blocks

# Kept deliberately strict: the output feeds the metadata extractor and the
# full-text index, so commentary or markdown fences would pollute both.
TRANSCRIPTION_PROMPT = (
    "Transcribe ALL text visible in this document image, exactly as written.\n"
    "Rules:\n"
    "- Preserve the original language of the document; do not translate.\n"
    "- Preserve reading order, line breaks and paragraph structure.\n"
    "- Render tables as plain text rows, keeping columns separated by ' | '.\n"
    "- Include headers, footers, page numbers, stamps, handwriting and totals.\n"
    "- Do NOT translate, summarise, correct or comment on the content.\n"
    "- Do NOT wrap the output in markdown code fences.\n"
    "- If the image contains no readable text, reply with exactly: [NO_TEXT_FOUND]"
)

NO_TEXT_SENTINEL = "[NO_TEXT_FOUND]"

# Formats a vision endpoint reliably accepts.
_ENCODE_FORMAT = "JPEG"
_ENCODE_MIME = "image/jpeg"

# Groq's rate-limit responses say how long to wait, e.g.
# "Please try again in 21.787499999s".
_RETRY_AFTER = re.compile(r"try again in\s+([0-9.]+)\s*s", re.IGNORECASE)

# Per-minute token limits are easy to hit on the free tier when transcribing a
# multi-page document. Waiting is far better than silently dropping a page.
MAX_RATE_LIMIT_RETRIES = 3
MAX_RATE_LIMIT_WAIT_SECONDS = 75.0


def _parse_retry_after(message: str) -> Optional[float]:
    match = _RETRY_AFTER.search(message)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _is_rate_limit(message: str) -> bool:
    lowered = message.lower()
    return (
        "rate_limit_exceeded" in lowered
        or "rate limit" in lowered
        or "tokens per minute" in lowered
        or "429" in lowered
    )


class VisionOCRError(RuntimeError):
    """Raised when the vision model cannot transcribe an image."""


class VisionOCR:
    """Transcribes images via a multimodal chat model."""

    def __init__(self, settings, client=None):
        self.settings = settings
        self._client = client
        self.model = AIClientFactory.get_vision_model(settings)
        self.max_bytes = int(getattr(settings, "vision_max_image_bytes", 4 * 1024 * 1024))
        self.max_pages = int(getattr(settings, "vision_max_pages", 20))

    @property
    def client(self):
        if self._client is None:
            self._client = AIClientFactory.create_client()
        return self._client

    # ------------------------------------------------------------------
    # Image preparation
    # ------------------------------------------------------------------
    def encode_image(self, image: Image.Image) -> str:
        """Return a base64 data URI, downscaling until it fits the size budget."""
        # Flatten alpha/palette modes; JPEG cannot store them.
        if image.mode not in ("RGB", "L"):
            if image.mode in ("RGBA", "LA", "P"):
                background = Image.new("RGB", image.size, (255, 255, 255))
                converted = image.convert("RGBA")
                background.paste(converted, mask=converted.split()[-1])
                image = background
            else:
                image = image.convert("RGB")

        # Cap the long edge first: OCR gains nothing above ~2000px and the
        # payload shrinks dramatically.
        max_edge = 2000
        if max(image.size) > max_edge:
            ratio = max_edge / float(max(image.size))
            new_size = (
                max(1, int(image.width * ratio)),
                max(1, int(image.height * ratio)),
            )
            image = image.resize(new_size, Image.LANCZOS)

        quality = 90
        while True:
            buffer = io.BytesIO()
            image.save(buffer, format=_ENCODE_FORMAT, quality=quality, optimize=True)
            data = buffer.getvalue()

            # base64 inflates by ~4/3.
            if len(data) * 4 / 3 <= self.max_bytes or quality <= 40:
                if len(data) * 4 / 3 > self.max_bytes:
                    # Still too big at the quality floor - shrink dimensions.
                    if max(image.size) <= 640:
                        raise VisionOCRError(
                            "Image cannot be compressed below the configured "
                            f"vision_max_image_bytes ({self.max_bytes} bytes)"
                        )
                    image = image.resize(
                        (max(1, image.width // 2), max(1, image.height // 2)),
                        Image.LANCZOS,
                    )
                    quality = 90
                    continue
                encoded = base64.b64encode(data).decode("ascii")
                return f"data:{_ENCODE_MIME};base64,{encoded}"

            quality -= 15

    # ------------------------------------------------------------------
    # Model call
    # ------------------------------------------------------------------
    def _build_request(self, data_uri: str, hint: Optional[str]) -> dict:
        text_prompt = TRANSCRIPTION_PROMPT
        if hint:
            text_prompt = f"{TRANSCRIPTION_PROMPT}\n\nContext: {hint}"

        params = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text_prompt},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
        }

        capabilities = AIClientFactory.get_capabilities(self.settings)
        token_param = capabilities.get("token_param", "max_tokens")
        params[token_param] = int(getattr(self.settings, "ai_max_tokens_vision", 2048))

        if capabilities.get("supports_temperature", True):
            # Transcription must be deterministic.
            params["temperature"] = 0.0

        if capabilities.get("supports_reasoning_effort", False):
            # Transcription is perception, not reasoning. Disabling it keeps the
            # output clean (hybrid models otherwise emit inline <think> blocks)
            # and leaves the whole token budget for the actual text.
            params["reasoning_effort"] = "none"

        return params

    def _request_with_rate_limit_retry(self, params: dict):
        """Send the request, waiting out per-minute token limits.

        The free tier's token-per-minute budget is easily exhausted partway
        through a multi-page document. Skipping the page would silently lose
        content, so honour the retry delay the API reports and try again.
        """
        last_error: Optional[Exception] = None

        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            try:
                return self.client.chat.completions.create(
                    **adapt_params(self.client, params)
                )
            except Exception as exc:
                message = str(exc)
                last_error = exc

                if not _is_rate_limit(message) or attempt == MAX_RATE_LIMIT_RETRIES:
                    break

                wait = _parse_retry_after(message)
                if wait is None:
                    wait = min(2 ** attempt * 5.0, MAX_RATE_LIMIT_WAIT_SECONDS)
                wait = min(wait + 0.5, MAX_RATE_LIMIT_WAIT_SECONDS)

                logger.info(
                    f"Vision model rate limited; waiting {wait:.1f}s before retry "
                    f"{attempt + 1}/{MAX_RATE_LIMIT_RETRIES}"
                )
                time.sleep(wait)

        message = str(last_error)
        if "413" in message or "too large" in message.lower():
            raise VisionOCRError(
                f"Vision model '{self.model}' rejected the request as too large for "
                "your per-minute token limit. Lower generation.max_tokens_vision or "
                "ocr.vision_max_image_bytes in config/models.json, or upgrade your "
                f"Groq tier. Original error: {message}"
            ) from last_error
        if _is_rate_limit(message):
            raise VisionOCRError(
                f"Vision model '{self.model}' stayed rate limited after "
                f"{MAX_RATE_LIMIT_RETRIES} retries. Upgrade your Groq tier or reduce "
                f"ocr.vision_max_pages. Original error: {message}"
            ) from last_error
        raise VisionOCRError(
            f"Vision model '{self.model}' request failed: {message}"
        ) from last_error

    def transcribe_image(self, image: Image.Image, hint: Optional[str] = None) -> str:
        """Transcribe a single PIL image. Returns '' when the page has no text."""
        data_uri = self.encode_image(image)
        params = self._build_request(data_uri, hint)

        response = self._request_with_rate_limit_retry(params)

        if not response.choices:
            raise VisionOCRError("Vision model returned no choices")

        content = response.choices[0].message.content or ""
        # Belt and braces: strip inline reasoning even though we asked for none.
        text = strip_reasoning_blocks(content).strip()

        # Some models still wrap output in fences despite the instruction.
        if text.startswith("```"):
            lines = text.split("\n")
            if len(lines) >= 2:
                lines = lines[1:]
                if lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                text = "\n".join(lines).strip()

        if text == NO_TEXT_SENTINEL or not text:
            return ""

        return text

    def transcribe_path(self, image_path: Path, hint: Optional[str] = None) -> str:
        """Transcribe an image file from disk."""
        with Image.open(image_path) as image:
            image.load()
            return self.transcribe_image(image, hint=hint)

    def transcribe_pages(
        self, pages: List[Image.Image], source_name: str = ""
    ) -> str:
        """Transcribe a list of page images, joining them with page markers."""
        if not pages:
            return ""

        total = len(pages)
        limit = min(total, self.max_pages)
        if total > limit:
            logger.warning(
                f"{source_name}: {total} pages exceed vision_max_pages={self.max_pages}; "
                f"only the first {limit} pages will be transcribed"
            )

        chunks: List[str] = []
        failures = 0
        for index in range(limit):
            hint = f"Page {index + 1} of {total}"
            if source_name:
                hint = f"{hint} of document '{source_name}'"
            try:
                page_text = self.transcribe_image(pages[index], hint=hint)
            except VisionOCRError as exc:
                failures += 1
                logger.warning(f"{source_name}: vision OCR failed on page {index + 1}: {exc}")
                # One bad page should not lose the whole document, but the gap
                # must be visible - a silently missing page looks like a page
                # that genuinely had no text.
                if failures >= 3 and not chunks:
                    raise
                chunks.append(
                    f"[Page {index + 1} of {total} could not be transcribed: {exc}]"
                )
                continue

            if page_text:
                chunks.append(page_text)

        if total > limit:
            chunks.append(
                f"[... {total - limit} further page(s) not transcribed "
                f"(vision_max_pages={self.max_pages}) ...]"
            )

        return "\n\n".join(chunks).strip()
