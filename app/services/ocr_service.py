"""Text extraction with a configurable engine chain.

Engine selection comes from the ``ocr_engine`` setting (``config/models.json``
-> ``ocr.engine``):

``auto`` (default)
    PDFs: embedded text layer -> vision model -> Tesseract.
    Images: vision model -> Tesseract.
``vision``
    Always use the vision model; Tesseract is only a last-resort fallback.
``tesseract``
    Classic local OCR only. The vision model is never called.
"""
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytesseract
from loguru import logger
from PIL import Image
from sqlalchemy.orm import Session

try:
    import pdf2image

    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    logger.warning("pdf2image not available. Rendering PDFs to images is disabled.")

try:
    from PyPDF2 import PdfReader

    PYPDF2_AVAILABLE = True
except ImportError:  # pragma: no cover - PyPDF2 is a hard requirement
    PYPDF2_AVAILABLE = False
    logger.warning("PyPDF2 not available. PDF text-layer extraction is disabled.")

from ..config import get_settings

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp"}
TEXT_EXTENSIONS = {".txt", ".text", ".md", ".markdown"}

# A PDF text layer is considered usable above this many non-whitespace chars.
MIN_TEXT_LAYER_CHARS = 100

# Resolving the tesseract binary shells out; cache it process-wide so that
# constructing an OCRService per request stays cheap.
_tesseract_lock = threading.Lock()
_tesseract_cmd: Optional[str] = None
_tesseract_resolved = False

# Poppler discovery walks the filesystem, so cache the answer per process.
_POPPLER_BINARY = "pdftoppm.exe" if os.name == "nt" else "pdftoppm"
_UNSET = object()
_poppler_cache: Dict[str, Any] = {}


def reset_poppler_cache():
    """Force re-detection (used after the poppler path setting changes)."""
    _poppler_cache.pop("path", None)


def _resolve_tesseract(configured_path: Optional[str]) -> Optional[str]:
    """Locate a working tesseract binary once per process."""
    global _tesseract_cmd, _tesseract_resolved

    with _tesseract_lock:
        if _tesseract_resolved:
            return _tesseract_cmd

        candidates = [
            # macOS (Homebrew)
            "/opt/homebrew/bin/tesseract",
            "/usr/local/bin/tesseract",
            "/usr/bin/tesseract",
            # Windows typical installs
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            # Fallback to PATH
            "tesseract",
        ]

        if configured_path and configured_path != "/usr/bin/tesseract":
            candidates.insert(0, configured_path)

        for path in candidates:
            try:
                result = subprocess.run(
                    [path, "--version"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    _tesseract_cmd = path
                    logger.info(f"Found working tesseract at: {path}")
                    break
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                continue
        else:
            logger.warning("No working tesseract installation found")
            if os.name == "nt":
                logger.warning(
                    "Windows install: winget install tesseract-ocr | choco install tesseract"
                )
            else:
                logger.warning(
                    "macOS: brew install tesseract | Linux: apt-get install tesseract-ocr"
                )

        _tesseract_resolved = True
        return _tesseract_cmd


def reset_tesseract_cache():
    """Force re-detection (used after the tesseract path setting changes)."""
    global _tesseract_cmd, _tesseract_resolved
    with _tesseract_lock:
        _tesseract_cmd = None
        _tesseract_resolved = False


class OCRService:
    def __init__(self, db: Session = None, settings=None, vision=None):
        self.settings = settings if settings is not None else get_settings(db)
        self._vision = vision
        self._vision_checked = vision is not None
        self.tesseract_cmd = _resolve_tesseract(
            getattr(self.settings, "tesseract_path", None)
        )
        if self.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

    # ------------------------------------------------------------------
    # Engine availability
    # ------------------------------------------------------------------
    @property
    def engine(self) -> str:
        return (getattr(self.settings, "ocr_engine", "auto") or "auto").lower()

    @property
    def tesseract_available(self) -> bool:
        return self.tesseract_cmd is not None

    @property
    def vision(self):
        """Lazily construct the vision client; ``None`` when unavailable."""
        if not self._vision_checked:
            self._vision_checked = True
            if not self.settings.vision_available:
                logger.debug("Vision OCR not available (disabled or no API key)")
                self._vision = None
            else:
                try:
                    from .vision_ocr import VisionOCR

                    self._vision = VisionOCR(self.settings)
                except Exception as exc:
                    logger.warning(f"Could not initialise vision OCR: {exc}")
                    self._vision = None
        return self._vision

    @property
    def vision_enabled(self) -> bool:
        return self.engine in ("auto", "vision") and self.vision is not None

    # ------------------------------------------------------------------
    # Individual extractors
    # ------------------------------------------------------------------
    def extract_text_from_image(self, image_path: Path) -> str:
        """Extract text from an image using the configured engine chain."""
        errors: List[str] = []

        if self.vision_enabled:
            try:
                text = self.vision.transcribe_path(image_path)
                if text:
                    logger.info(
                        f"Vision OCR extracted {len(text)} chars from {image_path.name}"
                    )
                    return text
                logger.info(
                    f"Vision OCR found no text in {image_path.name}; trying Tesseract"
                )
            except Exception as exc:
                errors.append(f"vision: {exc}")
                logger.warning(f"Vision OCR failed for {image_path.name}: {exc}")

        if self.engine == "vision" and not self.tesseract_available:
            raise RuntimeError(
                f"Vision OCR failed for {image_path.name} and Tesseract is not installed. "
                + ("; ".join(errors) if errors else "")
            )

        try:
            return self._tesseract_image(image_path)
        except Exception as exc:
            errors.append(f"tesseract: {exc}")
            raise RuntimeError(
                f"All OCR engines failed for {image_path.name}: {'; '.join(errors)}"
            ) from exc

    def _tesseract_image(self, image_path: Path) -> str:
        """Classic Tesseract OCR for a single image file."""
        if not self.tesseract_available:
            raise RuntimeError(
                "Tesseract is not installed. Install it, or set ocr.engine to "
                "'vision' in config/models.json with a vision model configured."
            )
        with Image.open(image_path) as image:
            config = "--oem 3 --psm 6"
            text = pytesseract.image_to_string(image, config=config)
            logger.info(f"Tesseract extracted text from image: {image_path.name}")
            return text.strip()

    def _tesseract_pil(self, image: Image.Image) -> str:
        if not self.tesseract_available:
            raise RuntimeError("Tesseract is not installed")
        return pytesseract.image_to_string(image, config="--oem 3 --psm 6").strip()

    def extract_pdf_text_layer(self, pdf_path: Path) -> str:
        """Read an embedded text layer from a digital PDF (no OCR, no poppler)."""
        if not PYPDF2_AVAILABLE:
            return ""
        try:
            reader = PdfReader(str(pdf_path))
            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception:
                    logger.info(f"{pdf_path.name}: encrypted PDF, skipping text layer")
                    return ""

            parts = []
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception as exc:
                    logger.debug(f"{pdf_path.name}: page text extraction failed: {exc}")
            return "\n\n".join(part for part in parts if part.strip()).strip()
        except Exception as exc:
            logger.info(f"{pdf_path.name}: no usable text layer ({exc})")
            return ""

    def _resolve_poppler_path(self) -> Optional[str]:
        """Locate the poppler bin directory, or None to fall back to PATH."""
        cached = _poppler_cache.get("path", _UNSET)
        if cached is not _UNSET:
            return cached

        resolved = self._detect_poppler_path()
        _poppler_cache["path"] = resolved
        return resolved

    def _detect_poppler_path(self) -> Optional[str]:
        configured = getattr(self.settings, "poppler_path", None)
        if configured and (Path(configured) / _POPPLER_BINARY).exists():
            return configured
        if configured and Path(configured).exists():
            # Directory exists but holds no poppler binary; keep looking.
            logger.debug(f"Configured poppler_path has no {_POPPLER_BINARY}: {configured}")

        if os.name != "nt":
            return None

        candidates = [
            Path(r"C:\Program Files\poppler\Library\bin"),
            Path(r"C:\Program Files\poppler\bin"),
        ]

        # winget installs to a versioned directory under the user's packages
        # folder, so glob rather than hard-coding a release number.
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            packages = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
            if packages.is_dir():
                try:
                    candidates.extend(
                        sorted(packages.glob("*Poppler*/**/Library/bin"), reverse=True)
                    )
                except OSError:
                    pass

        # Chocolatey / scoop / manual extraction.
        candidates.extend(
            [
                Path(r"C:\ProgramData\chocolatey\lib\poppler\tools\Library\bin"),
                Path(os.path.expanduser(r"~\scoop\apps\poppler\current\bin")),
            ]
        )

        for candidate in candidates:
            if (candidate / _POPPLER_BINARY).exists():
                logger.info(f"Using poppler at: {candidate}")
                return str(candidate)

        # Finally, trust PATH if pdftoppm is resolvable there.
        found = shutil.which(_POPPLER_BINARY) or shutil.which("pdftoppm")
        if found:
            logger.info(f"Using poppler from PATH: {found}")
            return str(Path(found).parent)

        return None

    def render_pdf_pages(self, pdf_path: Path, dpi: int = 200) -> List[Image.Image]:
        """Rasterise a PDF into page images (requires poppler)."""
        if not PDF2IMAGE_AVAILABLE:
            raise RuntimeError(
                "pdf2image is not installed; cannot rasterise PDF pages"
            )
        return pdf2image.convert_from_path(
            pdf_path, dpi=dpi, poppler_path=self._resolve_poppler_path()
        )

    def extract_text_from_pdf(self, pdf_path: Path) -> str:
        """Extract text from a PDF using the configured engine chain."""
        errors: List[str] = []

        # 1. Embedded text layer - free, exact, and covers most digital PDFs.
        if getattr(self.settings, "pdf_text_layer_first", True) and self.engine != "vision":
            text_layer = self.extract_pdf_text_layer(pdf_path)
            if len(text_layer.replace(" ", "").replace("\n", "")) >= MIN_TEXT_LAYER_CHARS:
                logger.info(
                    f"Extracted {len(text_layer)} chars from the text layer of {pdf_path.name}"
                )
                return text_layer
            if text_layer:
                logger.info(
                    f"{pdf_path.name}: text layer too sparse "
                    f"({len(text_layer)} chars), falling back to OCR"
                )

        # 2. Rasterise, then OCR each page.
        try:
            pages = self.render_pdf_pages(pdf_path)
        except Exception as exc:
            errors.append(f"render: {exc}")
            logger.warning(f"Could not rasterise {pdf_path.name}: {exc}")

            # Last resort: return whatever the text layer had, even if sparse.
            fallback = self.extract_pdf_text_layer(pdf_path)
            if fallback.strip():
                logger.info(f"{pdf_path.name}: using sparse text layer as fallback")
                return fallback

            raise RuntimeError(
                f"Cannot read {pdf_path.name}: no text layer and PDF rendering "
                f"failed ({'; '.join(errors)}). Install poppler for scanned PDFs."
            ) from exc

        logger.info(f"{pdf_path.name}: rendered {len(pages)} page(s)")

        try:
            if self.vision_enabled:
                try:
                    text = self.vision.transcribe_pages(pages, source_name=pdf_path.name)
                    if text:
                        logger.info(
                            f"Vision OCR extracted {len(text)} chars from {pdf_path.name}"
                        )
                        return text
                    logger.info(
                        f"Vision OCR found no text in {pdf_path.name}; trying Tesseract"
                    )
                except Exception as exc:
                    errors.append(f"vision: {exc}")
                    logger.warning(f"Vision OCR failed for {pdf_path.name}: {exc}")

            # 3. Tesseract over the rendered pages.
            try:
                return self._tesseract_pages(pages, pdf_path.name)
            except Exception as exc:
                errors.append(f"tesseract: {exc}")
                raise RuntimeError(
                    f"All OCR engines failed for {pdf_path.name}: {'; '.join(errors)}"
                ) from exc
        finally:
            for page in pages:
                try:
                    page.close()
                except Exception:
                    pass

    def _tesseract_pages(self, pages: List[Image.Image], name: str) -> str:
        if not self.tesseract_available:
            raise RuntimeError(
                "Tesseract is not installed. Install it, or configure a vision "
                "model in config/models.json."
            )

        all_text = []
        for index, page in enumerate(pages):
            logger.debug(f"Tesseract processing page {index + 1} of {name}")
            try:
                page_text = self._tesseract_pil(page)
            except Exception as exc:
                logger.warning(f"{name}: Tesseract failed on page {index + 1}: {exc}")
                continue
            if page_text:
                all_text.append(page_text)

        text = "\n\n".join(all_text).strip()
        logger.info(f"Tesseract extracted {len(text)} chars from {name}")
        return text

    def extract_text_from_text_file(self, text_path: Path) -> str:
        """Extract text from a plain text file"""
        try:
            encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"]

            for encoding in encodings:
                try:
                    with open(text_path, "r", encoding=encoding) as file:
                        text = file.read()
                        logger.info(
                            f"Successfully read text file: {text_path.name} (encoding: {encoding})"
                        )
                        return text.strip()
                except UnicodeDecodeError:
                    continue

            with open(text_path, "r", encoding="utf-8", errors="replace") as file:
                text = file.read()
                logger.warning(
                    f"Read text file with character replacement: {text_path.name}"
                )
                return text.strip()

        except Exception as e:
            logger.error(f"Failed to read text file {text_path}: {e}")
            raise

    def extract_text(self, file_path: Path) -> str:
        """Extract text from a file based on its type"""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        file_extension = file_path.suffix.lower()

        try:
            if file_extension == ".pdf":
                return self.extract_text_from_pdf(file_path)
            elif file_extension in IMAGE_EXTENSIONS:
                return self.extract_text_from_image(file_path)
            elif file_extension in TEXT_EXTENSIONS:
                return self.extract_text_from_text_file(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_extension}")

        except Exception as e:
            logger.error(f"Text extraction failed for {file_path}: {e}")
            raise

    def get_ocr_confidence(self, file_path: Path) -> Optional[float]:
        """Get Tesseract's OCR confidence score for an image file."""
        if not self.tesseract_available:
            return None
        try:
            if file_path.suffix.lower() == ".pdf":
                # Would require per-page processing; not worth the cost here.
                return None
            with Image.open(file_path) as image:
                data = pytesseract.image_to_data(
                    image, output_type=pytesseract.Output.DICT
                )
                confidences = [int(c) for c in data["conf"] if int(c) > 0]
                if confidences:
                    return sum(confidences) / len(confidences) / 100.0
                return None
        except Exception as e:
            logger.warning(f"Could not calculate OCR confidence for {file_path}: {e}")
            return None

    def describe(self) -> dict:
        """Diagnostics for the health endpoint."""
        poppler = self._resolve_poppler_path()
        return {
            "engine": self.engine,
            "tesseract_available": self.tesseract_available,
            "tesseract_path": self.tesseract_cmd,
            "vision_enabled": self.vision_enabled,
            "vision_model": getattr(self.settings, "vision_model", None),
            # Rendering scanned PDFs needs both the python binding and the
            # poppler binaries; report them together so the health endpoint
            # cannot claim readiness when only one is present.
            "pdf_render_available": PDF2IMAGE_AVAILABLE and poppler is not None,
            "pdf2image_installed": PDF2IMAGE_AVAILABLE,
            "poppler_path": poppler,
            "pdf_text_layer_available": PYPDF2_AVAILABLE,
        }
