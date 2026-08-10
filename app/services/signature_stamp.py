"""
Stamping approval signatures onto the document itself.

Two things had to be true for this to be worth building:

  * it must work on **any** PDF, not just the ones written in the Studio. A
    scanned invoice that went through three approvers deserves the same signed
    rendition as a composed letter, so signatures are drawn as an **overlay**
    and merged onto the existing pages rather than re-flowed into the source.

  * the approved bytes must survive. Stamping never edits a file in place: it
    returns new bytes, and the caller decides whether that becomes a new
    version. The version that was approved stays exactly as it was approved.

Placement is held as a fraction of the page rather than in millimetres, so a
block sits in the same visual place whether the page is A4, Letter, or a scan
at some arbitrary size.
"""
from __future__ import annotations

import base64
import binascii
import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from loguru import logger

from ..utils import ist
from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

# The block: a signature image over a rule, with the name, the designation and
# when it was signed underneath. Sized in points, which is what PDF works in.
BLOCK_W = 158.0          # default width of one block
IMAGE_H = 30.0           # the mark itself
RULE_GAP = 3.0
LINE_NAME = 9.0
LINE_ROLE = 7.6
LINE_META = 6.6
BLOCK_H = IMAGE_H + RULE_GAP + LINE_NAME + LINE_ROLE + LINE_META + 14.0

# Where the automatic layout puts things: a band across the bottom of the page.
MARGIN_X = 46.0
BAND_BOTTOM = 88.0       # sits above the footer furniture, not on top of it
COLUMNS = 3

# Anything wholly inside this band at the foot of the page is page furniture -
# a running footer, an address line, a page number - not body content. Counting
# it as content would make every letterheaded page look full to the bottom edge,
# and no document would ever qualify for signatures on its last page.
FOOTER_ZONE = 80.0
COL_GAP = 18.0
ROW_GAP = 12.0
MAX_AUTO_ROWS = 2        # beyond this, signatures get their own page

INK = colors.HexColor("#16181D")
QUIET = colors.HexColor("#6B707A")
FAINT = colors.HexColor("#9AA0A8")
RULE = colors.HexColor("#2E3138")


@dataclass
class Block:
    """One signature, and where it goes."""
    signature_id: str
    name: str
    designation: str = ""
    data_url: str = ""
    signed_at: Optional[datetime] = None
    step_name: str = ""
    order: int = 0

    # Fractions of the page. None means "the automatic layout decides".
    page_number: Optional[int] = None
    x_pct: Optional[float] = None
    y_pct: Optional[float] = None
    width_pct: Optional[float] = None

    # Filled in by resolve(); always concrete afterwards.
    resolved: dict = field(default_factory=dict)


class StampError(RuntimeError):
    """The document could not be signed."""


# ------------------------------------------------------------------ geometry


def page_geometry(pdf_bytes: bytes) -> list[dict]:
    """Width and height of every page, in points."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        out = []
        for page in reader.pages:
            box = page.mediabox
            out.append({
                "width": float(box.width),
                "height": float(box.height),
            })
        return out
    except Exception as exc:
        raise StampError(f"That file could not be read as a PDF: {exc}") from exc


def content_bottom(pdf_bytes: bytes, page_number: int) -> Optional[float]:
    """
    How far up the page the *body* text reaches, measured from the bottom edge.

    Used to decide whether approval signatures actually fit under the last
    paragraph. Guessing a fixed band puts them on top of a footer or through
    the author's own sign-off, which is exactly the failure this avoids.

    Text lying wholly inside the footer band is skipped: it is furniture that
    repeats on every page, and treating it as content would mean no letterheaded
    document ever had room for a signature.

    Returns None when the page cannot be measured - a scan with no text layer,
    say - in which case the caller should assume there is no room.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None

    try:
        doc = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
        index = max(0, min(page_number - 1, len(doc) - 1))
        textpage = doc[index].get_textpage()
        count = textpage.count_chars()
        if not count:
            return None

        lowest = None
        for i in range(count):
            try:
                box = textpage.get_charbox(i)     # left, bottom, right, top
            except Exception:
                continue
            if not box:
                continue
            bottom, top = box[1], box[3]
            if top <= FOOTER_ZONE:      # page furniture, not body content
                continue
            if lowest is None or bottom < lowest:
                lowest = bottom

        # Nothing but furniture on the page: the whole body area is free.
        return lowest if lowest is not None else float(doc[index].get_height())
    except Exception as exc:
        logger.debug(f"Could not measure page content: {exc}")
        return None


def resolve(blocks: list[Block], geometry: list[dict],
            pdf_bytes: Optional[bytes] = None) -> list[Block]:
    """
    Give every block a concrete page and position.

    A block that has been positioned by hand keeps exactly where it was put.
    Everything else is laid out automatically: along the bottom of the last
    page when there is genuinely room under the text, and otherwise on a
    dedicated signature sheet appended to the document.

    Choosing the sheet is not a failure. A one-page report that already carries
    the author's own sign-off has nowhere sensible to put three more marks, and
    an appended sheet is what an auditor expects to find anyway.
    """
    if not geometry:
        raise StampError("That document has no pages.")

    last = len(geometry)
    page = geometry[last - 1]
    page_w, page_h = page["width"], page["height"]

    auto = [b for b in blocks if b.page_number is None or b.x_pct is None]
    rows_needed = (len(auto) + COLUMNS - 1) // COLUMNS if auto else 0

    overflow = rows_needed > MAX_AUTO_ROWS

    # Does the last page have room under its text for the rows we need?
    if auto and not overflow and pdf_bytes is not None:
        reach = content_bottom(pdf_bytes, last)
        needed = BAND_BOTTOM + rows_needed * (BLOCK_H + ROW_GAP) + 10
        if reach is None or reach < needed:
            overflow = True

    # The band the automatic layout may use on the last page.
    usable_w = page_w - (MARGIN_X * 2)
    col_w = (usable_w - COL_GAP * (COLUMNS - 1)) / COLUMNS

    slot = 0
    for b in blocks:
        if b.page_number is not None and b.x_pct is not None:
            # Placed by hand. Trust it, but keep it on the page.
            target_page = max(1, min(int(b.page_number), last + 1))
            geo = geometry[target_page - 1] if target_page <= last else {"width": page_w, "height": page_h}
            width = (b.width_pct or (BLOCK_W / geo["width"])) * geo["width"]
            x = max(0.0, min(float(b.x_pct), 1.0)) * geo["width"]
            y_top = max(0.0, min(float(b.y_pct), 1.0)) * geo["height"]
            b.resolved = {
                "page": target_page,
                "x": min(x, geo["width"] - 8),
                "y_top": y_top,
                "width": max(70.0, min(width, geo["width"] - 16)),
                "page_width": geo["width"],
                "page_height": geo["height"],
                "auto": False,
            }
            continue

        if overflow:
            # A dedicated page after the document, laid out generously.
            index = slot
            row, col = divmod(index, COLUMNS)
            x = MARGIN_X + col * (col_w + COL_GAP)
            y_top = 130.0 + row * (BLOCK_H + ROW_GAP + 14)
            b.resolved = {
                "page": last + 1, "x": x, "y_top": y_top, "width": col_w,
                "page_width": page_w, "page_height": page_h, "auto": True,
            }
        else:
            row, col = divmod(slot, COLUMNS)
            x = MARGIN_X + col * (col_w + COL_GAP)
            # Rows stack upward from the bottom band.
            baseline = BAND_BOTTOM + (row * (BLOCK_H + ROW_GAP))
            y_top = page_h - (baseline + BLOCK_H)
            b.resolved = {
                "page": last, "x": x, "y_top": y_top, "width": col_w,
                "page_width": page_w, "page_height": page_h, "auto": True,
            }
        slot += 1

    return blocks


# ------------------------------------------------------------------ drawing


def _image(data_url: str):
    """Decode a signature data URL into something ReportLab can draw."""
    if not data_url or not data_url.startswith("data:image/"):
        return None
    try:
        head, _, payload = data_url.partition(",")
        if "base64" not in head:
            return None
        raw = base64.b64decode(payload, validate=False)
        return ImageReader(io.BytesIO(raw))
    except (binascii.Error, ValueError, OSError):
        return None


def _draw_block(c: rl_canvas.Canvas, b: Block) -> None:
    """
    One signature block, drawn from its top-left corner downward.

    PDF coordinates start at the bottom-left, which is the opposite of how
    anybody places something on a page. The block is positioned by its top edge
    and converted here, once, so nothing above this has to think about it.
    """
    r = b.resolved
    width = r["width"]
    x = r["x"]
    top = r["page_height"] - r["y_top"]      # flip to PDF space

    # The mark
    y = top - IMAGE_H
    img = _image(b.data_url)
    if img:
        try:
            iw, ih = img.getSize()
            draw_h = IMAGE_H
            draw_w = draw_h * (iw / ih) if ih else width
            if draw_w > width:
                draw_w = width
                draw_h = draw_w * (ih / iw) if iw else IMAGE_H
            c.drawImage(img, x, top - draw_h, width=draw_w, height=draw_h, mask="auto")
        except Exception as exc:
            logger.warning(f"Signature image could not be drawn: {exc}")

    # The rule it sits on
    y -= RULE_GAP
    c.setStrokeColor(RULE)
    c.setLineWidth(0.8)
    c.line(x, y, x + width, y)

    # Name
    y -= LINE_NAME + 2
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", LINE_NAME)
    c.drawString(x, y, _fit(c, b.name or "", "Helvetica-Bold", LINE_NAME, width))

    # Designation
    if b.designation:
        y -= LINE_ROLE + 2
        c.setFillColor(QUIET)
        c.setFont("Helvetica", LINE_ROLE)
        c.drawString(x, y, _fit(c, b.designation, "Helvetica", LINE_ROLE, width))

    # What they approved, and when
    y -= LINE_META + 2.5
    c.setFillColor(FAINT)
    c.setFont("Helvetica", LINE_META)
    # Stored in UTC, printed in IST. Without the conversion a document signed
    # at 09:00 in Bengaluru carried 03:30 on its face.
    when = ist.fmt(b.signed_at, ist.DATE_TIME_LONG)
    meta = " · ".join(p for p in (b.step_name, when) if p)
    c.drawString(x, y, _fit(c, meta, "Helvetica", LINE_META, width))


def _fit(c: rl_canvas.Canvas, text: str, font: str, size: float, width: float) -> str:
    """Trim to the block width rather than letting a long title overrun it."""
    if not text:
        return ""
    if c.stringWidth(text, font, size) <= width:
        return text
    while text and c.stringWidth(text + "…", font, size) > width:
        text = text[:-1]
    return text + "…"


def _signature_page_header(c: rl_canvas.Canvas, width: float, height: float,
                           title: str, count: int) -> None:
    """Title the overflow page, so it is not a sheet of floating names."""
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 15)
    c.drawString(MARGIN_X, height - 62, "Approval signatures")

    c.setFillColor(QUIET)
    c.setFont("Helvetica", 9)
    c.drawString(MARGIN_X, height - 78, _fit(c, title, "Helvetica", 9, width - MARGIN_X * 2))

    c.setFillColor(FAINT)
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN_X, height - 92,
                 f"{count} approver{'' if count == 1 else 's'} · "
                 f"recorded by the HARMAN Document Management System")

    c.setStrokeColor(colors.HexColor("#E6E8EC"))
    c.setLineWidth(0.8)
    c.line(MARGIN_X, height - 102, width - MARGIN_X, height - 102)


# ------------------------------------------------------------------- stamp


def stamp(pdf_bytes: bytes, blocks: list[Block], title: str = "") -> bytes:
    """
    Return a copy of the PDF with the signature blocks drawn on it.

    The input is never modified. If a block is placed on the page after the
    last one, that page is created and titled.
    """
    if not blocks:
        return pdf_bytes

    geometry = page_geometry(pdf_bytes)
    blocks = resolve(blocks, geometry, pdf_bytes)

    by_page: dict[int, list[Block]] = {}
    for b in blocks:
        by_page.setdefault(b.resolved["page"], []).append(b)

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()

        for index, page in enumerate(reader.pages, start=1):
            here = by_page.get(index)
            if here:
                box = page.mediabox
                overlay = _overlay(float(box.width), float(box.height), here)
                page.merge_page(overlay)
            writer.add_page(page)

        # Anything addressed to a page beyond the document gets a new sheet.
        extra = sorted(p for p in by_page if p > len(reader.pages))
        for page_no in extra:
            here = by_page[page_no]
            geo = geometry[-1]
            overlay = _overlay(geo["width"], geo["height"], here,
                               header=(title, len(blocks)))
            writer.add_page(overlay)

        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()

    except StampError:
        raise
    except Exception as exc:
        logger.exception("Signature stamping failed")
        raise StampError(f"The signatures could not be applied: {exc}") from exc


def _overlay(width: float, height: float, blocks: list[Block],
             header: Optional[tuple] = None):
    """Build a single-page PDF holding just the blocks, ready to merge."""
    buffer = io.BytesIO()
    c = rl_canvas.Canvas(buffer, pagesize=(width, height))

    if header:
        _signature_page_header(c, width, height, header[0], header[1])

    for b in blocks:
        _draw_block(c, b)

    c.showPage()
    c.save()
    buffer.seek(0)
    return PdfReader(buffer).pages[0]


# ------------------------------------------------------- page image, for the UI


def render_page_png(pdf_bytes: bytes, page_number: int = 1, scale: float = 1.6) -> bytes:
    """
    Render one page to PNG, so the placement editor has the real page behind it.

    Uses PDFium (BSD/Apache), which needs no system libraries. Without a true
    picture of the page you cannot tell whether a signature is sitting on top
    of a paragraph, which is the whole reason the editor exists.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise StampError(
            "Page previews need pypdfium2. Install it with: pip install pypdfium2"
        ) from exc

    try:
        doc = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
        index = max(0, min(page_number - 1, len(doc) - 1))
        image = doc[index].render(scale=scale).to_pil()
        out = io.BytesIO()
        image.save(out, "PNG", optimize=True)
        return out.getvalue()
    except Exception as exc:
        raise StampError(f"That page could not be rendered: {exc}") from exc


# ------------------------------------------------------------------ helpers


def blocks_from_workflow(workflow) -> list[Block]:
    """
    The signature blocks for an approval, in the order the steps ran.

    Only steps that were approved *and* carry a signature contribute. A step
    marked "approval only" produced no signature and must not appear as one.

    A step that required everybody has one signature per approver, held on the
    individual decisions. All of them are stamped: the point of asking three
    people to sign is that the document ends up carrying three signatures.
    The step's own `signature` is the closing one and is already among them,
    so it is only used when there are no individual records - which is every
    approval made before this existed.
    """
    out = []
    for step in sorted(workflow.steps, key=lambda s: s.order_index):
        if step.status != "approved":
            continue

        signed = [d.signature for d in (getattr(step, "decisions", None) or [])
                  if d.action == "approved" and d.signature]
        if not signed and step.signature:
            signed = [step.signature]

        for sig in signed:
            out.append(Block(
                signature_id=sig.id,
                name=sig.name or "",
                designation=sig.designation or "",
                data_url=sig.data_url or "",
                signed_at=sig.signed_at,
                step_name=step.name or "",
                order=step.order_index + 1,
                page_number=sig.page_number,
                x_pct=sig.x_pct,
                y_pct=sig.y_pct,
                width_pct=sig.width_pct,
            ))
    return out


def default_width_pct(page_width: float) -> float:
    """The block width the automatic layout uses, as a fraction of the page."""
    usable = page_width - (MARGIN_X * 2)
    return ((usable - COL_GAP * (COLUMNS - 1)) / COLUMNS) / page_width
