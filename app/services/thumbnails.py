"""
Page-one thumbnails, so a file can be recognised before it is opened.

Somebody who has just dropped three files in wants to know at a glance that
they dropped the right three. A filename does not tell them that - the whole
point of a document management system is that filenames lie. A picture of the
first page does.

Only two kinds of file can actually be pictured: PDFs, rendered with PDFium,
and images, which are their own thumbnail. Word, Excel and plain text return
None and the caller draws a typed placeholder instead. Rendering a .docx would
mean shelling out to an office suite, and a placeholder that is honest about
being a placeholder beats a preview that takes eight seconds to appear.

Thumbnails are cached on disk under data/thumbnails and keyed by the source
file's modification time, so replacing a document invalidates its thumbnail
without anything having to remember to delete it.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Optional

from loguru import logger

CACHE_DIR = Path("data") / "thumbnails"
WIDTH = 520          # enough for a 260 px card on a 2x display
MAX_SOURCE_BYTES = 120 * 1024 * 1024

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}


class ThumbnailError(RuntimeError):
    """The file could not be pictured. Callers fall back to a placeholder."""


def _cache_path(document_id: str, source: Path) -> Path:
    try:
        stamp = int(source.stat().st_mtime)
    except OSError:
        stamp = 0
    return CACHE_DIR / f"{document_id}-{stamp}.png"


def _fit(image, width: int = WIDTH):
    """Downscale to `width`, never up. Upscaling a 90 px icon helps nobody."""
    if image.width <= width:
        return image
    from PIL import Image

    height = max(1, round(image.height * width / image.width))
    return image.resize((width, height), Image.LANCZOS)


def _flatten(image):
    """
    Put transparency on white.

    A thumbnail is shown on a white card. Left as RGBA, a transparent scan
    renders as whatever is behind it, which reads as a corrupted file.
    """
    from PIL import Image

    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        canvas = Image.new("RGB", image.size, (255, 255, 255))
        canvas.paste(image, mask=image.split()[-1])
        return canvas
    return image.convert("RGB")


def _from_pdf(source: Path) -> bytes:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(source))
    if not len(doc):
        raise ThumbnailError("The PDF has no pages")
    # Render a little above target and downscale: PDFium's own scaling of text
    # at thumbnail size is noticeably coarser than Lanczos on a larger raster.
    page = doc[0]
    scale = min(2.0, max(0.6, WIDTH / max(1.0, page.get_width())))
    image = _fit(_flatten(page.render(scale=scale).to_pil()))
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def _from_image(source: Path) -> bytes:
    from PIL import Image

    with Image.open(source) as handle:
        handle.load()
        image = _fit(_flatten(handle))
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def can_render(source: Path, mime: Optional[str] = None) -> bool:
    suffix = source.suffix.lower()
    if suffix == ".pdf" or (mime or "") == "application/pdf":
        return True
    return suffix in IMAGE_SUFFIXES or (mime or "").startswith("image/")


def thumbnail(document_id: str, source: Path, mime: Optional[str] = None) -> Optional[bytes]:
    """
    A PNG of the document's first page, or None when it cannot be pictured.

    Never raises for an unreadable file: a broken thumbnail must not break the
    screen it appears on.
    """
    if not source.exists() or not can_render(source, mime):
        return None
    try:
        if source.stat().st_size > MAX_SOURCE_BYTES:
            return None
    except OSError:
        return None

    cached = _cache_path(document_id, source)
    if cached.exists():
        try:
            return cached.read_bytes()
        except OSError:
            pass

    try:
        suffix = source.suffix.lower()
        is_pdf = suffix == ".pdf" or (mime or "") == "application/pdf"
        data = _from_pdf(source) if is_pdf else _from_image(source)
    except Exception as exc:
        logger.debug(f"No thumbnail for {source.name}: {exc}")
        return None

    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(data)
        # A replaced file leaves its old thumbnail behind, so sweep the stale
        # ones for this document while we are here.
        for old in CACHE_DIR.glob(f"{document_id}-*.png"):
            if old != cached:
                old.unlink(missing_ok=True)
    except OSError as exc:
        logger.debug(f"Could not cache thumbnail for {source.name}: {exc}")

    return data
