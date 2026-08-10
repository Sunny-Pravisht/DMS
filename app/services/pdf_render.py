"""
Turn a composed document into a PDF that matches the Studio canvas.

Two halves:

  * `_paint_chrome` draws the letterhead on every page, straight from the
    template spec in `doc_templates.py` - the same numbers the browser uses.
  * `_Blocks` walks the body HTML and produces ReportLab flowables.

The HTML is sanitised before it gets here, and again here, because this module
is also reachable from the API and must never trust its input. Anything it does
not recognise is dropped rather than guessed at.

Only ReportLab's own Helvetica family is used, so there is no font to install
and the output is identical on a developer laptop and in the container.
"""
from __future__ import annotations

import base64
import binascii
import io
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

import bleach
from loguru import logger
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .doc_templates import get_template

BRAND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "ui" / "assets" / "brand"

# What a body may contain. Everything else is stripped, including any styling
# that could smuggle in a URL.
ALLOWED_TAGS = [
    "h1", "h2", "h3", "h4", "p", "br", "hr", "div", "span",
    "strong", "b", "em", "i", "u", "s", "strike", "sub", "sup",
    "ul", "ol", "li", "blockquote", "table", "thead", "tbody", "tr", "th", "td",
    "img", "a",
    # Some browsers still emit <font> from execCommand. Allowing it means the
    # colour a user picked survives the round trip instead of being stripped.
    "font",
]
ALLOWED_ATTRS = {
    "*": ["class", "style", "align", "data-sig-block", "data-asset", "data-size"],
    "font": ["color", "size", "face"],
    "img": ["src", "alt", "width", "height", "class", "style", "data-asset", "data-size"],
    "a": ["href", "title"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}
ALLOWED_PROTOCOLS = ["http", "https", "data"]

# Inline styles worth keeping. Alignment, colour and weight survive; anything
# that could move an element off the page or reference a URL does not.
ALLOWED_CSS_PROPERTIES = [
    "text-align", "color", "background-color",
    "font-size", "font-weight", "font-style", "text-decoration",
    "width", "height", "margin-left", "padding-left",
]

try:
    from bleach.css_sanitizer import CSSSanitizer

    _CSS_SANITIZER = CSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES)
except Exception:  # tinycss2 absent: drop styles rather than trust them
    _CSS_SANITIZER = None

MAX_EMBEDDED_IMAGE_BYTES = 8 * 1024 * 1024


class RenderError(RuntimeError):
    """The body could not be turned into a PDF."""


# ---------------------------------------------------------------- sanitising


def sanitize_html(html: str) -> str:
    """Strip the body down to the subset both renderers agree on."""
    if not html:
        return ""

    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        css_sanitizer=_CSS_SANITIZER,
        strip=True,
    )


def html_to_text(html: str) -> str:
    """
    A plain-text rendering of the body, used for the full-text index, search
    and the AI pipeline. Block boundaries become newlines so sentences from
    different paragraphs never run together.
    """
    if not html:
        return ""

    text = re.sub(r"(?is)<(br|/p|/h[1-6]|/li|/tr|/div|/blockquote)[^>]*>", "\n", html)
    text = re.sub(r"(?is)</t[dh]>", "\t", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
    )
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ------------------------------------------------------------------- styles


def _styles(spec: dict) -> dict:
    ink = colors.HexColor(spec.get("ink") or "#16181D")
    accent = colors.HexColor(spec.get("accent_dark") or spec.get("accent") or "#006499")

    base = ParagraphStyle(
        "body",
        fontName="Helvetica",
        fontSize=10.5,
        leading=15.5,
        textColor=ink,
        spaceAfter=7,
        alignment=TA_LEFT,
    )
    return {
        "p": base,
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=17,
                             leading=22, textColor=accent, spaceBefore=6, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=13,
                             leading=17, textColor=ink, spaceBefore=12, spaceAfter=6),
        "h3": ParagraphStyle("h3", parent=base, fontName="Helvetica-Bold", fontSize=11.5,
                             leading=15, textColor=ink, spaceBefore=10, spaceAfter=4),
        "h4": ParagraphStyle("h4", parent=base, fontName="Helvetica-Bold", fontSize=10.5,
                             leading=14, textColor=ink, spaceBefore=8, spaceAfter=3),
        "meta": ParagraphStyle("meta", parent=base, fontSize=9, leading=13,
                               textColor=colors.HexColor("#6B707A"), spaceAfter=12),
        "quote": ParagraphStyle("quote", parent=base, leftIndent=10 * mm, rightIndent=4 * mm,
                                textColor=colors.HexColor("#4B5058"), fontName="Helvetica-Oblique"),
        "li": ParagraphStyle("li", parent=base, spaceAfter=3),
        "th": ParagraphStyle("th", parent=base, fontName="Helvetica-Bold", fontSize=9.5,
                             leading=13, spaceAfter=0, textColor=colors.white),
        "td": ParagraphStyle("td", parent=base, fontSize=9.5, leading=13, spaceAfter=0),
        "sigrole": ParagraphStyle("sigrole", parent=base, fontSize=9, leading=12.5,
                                  textColor=colors.HexColor("#6B707A"), spaceAfter=0),
        "signame": ParagraphStyle("signame", parent=base, fontName="Helvetica-Bold",
                                  fontSize=10.5, leading=14, spaceAfter=1),
    }


# ------------------------------------------------------------- HTML → blocks

_INLINE_MAP = {
    "strong": ("<b>", "</b>"), "b": ("<b>", "</b>"),
    "em": ("<i>", "</i>"), "i": ("<i>", "</i>"),
    "u": ("<u>", "</u>"),
    "s": ("<strike>", "</strike>"), "strike": ("<strike>", "</strike>"),
    "sub": ("<sub>", "</sub>"), "sup": ("<super>", "</super>"),
}

_BLOCK_TAGS = {"h1", "h2", "h3", "h4", "p", "div", "blockquote", "li"}


def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _css_colour(value: str) -> str:
    """
    Normalise a CSS colour to something ReportLab accepts.

    Browsers report computed colours as `rgb(r, g, b)`, which ReportLab's
    mini-markup does not parse, so convert those to hex and pass the rest
    through. An unparseable value falls back to the body colour rather than
    raising: a wrong shade is a smaller failure than a document that will not
    render at all.
    """
    value = (value or "").strip().rstrip(";").strip()

    rgb = re.match(r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", value, re.I)
    if rgb:
        r, g, b = (min(255, int(rgb.group(i))) for i in (1, 2, 3))
        return f"#{r:02X}{g:02X}{b:02X}"

    if re.fullmatch(r"#[0-9A-Fa-f]{3}|#[0-9A-Fa-f]{6}", value):
        return value
    if re.fullmatch(r"[a-zA-Z]+", value):
        return value.lower()
    return "#16181D"


def _css_points(style: str) -> Optional[int]:
    """Pull a font size out of an inline style, in points."""
    m = re.search(r"font-size\s*:\s*([\d.]+)\s*(pt|px|em|rem)?", style or "", re.I)
    if not m:
        return None
    value = float(m.group(1))
    unit = (m.group(2) or "px").lower()
    points = {
        "pt": value,
        "px": value * 0.75,
        "em": value * 10.5,
        "rem": value * 10.5,
    }.get(unit, value * 0.75)
    return max(6, min(48, round(points)))


def _legacy_font_size(size: Optional[str]) -> Optional[int]:
    """`<font size="1..7">`, which execCommand('fontSize') still emits."""
    if not size or not str(size).strip().isdigit():
        return None
    return {1: 7, 2: 9, 3: 10, 4: 12, 5: 15, 6: 20, 7: 28}.get(int(size))


def _align_from(style: str, align_attr: str) -> Optional[int]:
    value = (align_attr or "").lower()
    if not value and style:
        m = re.search(r"text-align\s*:\s*([a-z]+)", style, re.I)
        value = m.group(1).lower() if m else ""
    return {
        "center": TA_CENTER, "right": TA_RIGHT,
        "justify": TA_JUSTIFY, "left": TA_LEFT,
    }.get(value)


class _Blocks(HTMLParser):
    """
    Walk sanitised HTML and emit ReportLab flowables.

    Inline formatting is re-expressed in ReportLab's own mini-markup, which
    Paragraph understands. Block elements close the buffer and flush it.
    """

    def __init__(self, styles: dict, content_width: float, asset_resolver=None):
        super().__init__(convert_charrefs=True)
        self.st = styles
        self.width = content_width
        self.resolve = asset_resolver or (lambda src: None)

        self.flow: list = []
        self.buf: list[str] = []
        self.block = "p"
        self.align: Optional[int] = None
        self.klass = ""

        self._list_stack: list[dict] = []
        self._table: Optional[dict] = None
        # A signature block contains its own divs (the rule, the name, the
        # role), so track nesting: only the div that opened the block closes it.
        self._in_sig = False
        self._sig_depth = 0
        self._sig: dict = {}

    # -- buffer -----------------------------------------------------------
    def _flush(self):
        text = "".join(self.buf).strip()
        self.buf = []
        if not text:
            return

        style = self.st.get(self.block, self.st["p"])
        if "doc-meta" in self.klass:
            style = self.st["meta"]
        if self.align is not None:
            style = ParagraphStyle(style.name + "-a", parent=style, alignment=self.align)

        para = Paragraph(text, style)

        if self._list_stack:
            self._list_stack[-1]["items"].append(ListItem(para, leftIndent=6 * mm))
        elif self._table is not None and self._table["row"] is not None:
            self._table["row"].append(para)
        elif self._in_sig:
            self._sig.setdefault("lines", []).append(para)
        else:
            self.flow.append(para)

    # -- tags -------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        style = a.get("style", "")
        klass = a.get("class", "")

        if tag in _INLINE_MAP:
            self.buf.append(_INLINE_MAP[tag][0])
            return

        if tag == "br":
            self.buf.append("<br/>")
            return

        # ReportLab's Paragraph speaks <font color=… size=…> natively, so any
        # inline colour or size the editor produced maps straight onto it.
        if tag in ("span", "font"):
            attrs_out = []

            colour = a.get("color") or ""
            if not colour:
                m = re.search(r"(?<![-a-z])color\s*:\s*([^;]+)", style, re.I)
                colour = m.group(1).strip() if m else ""
            if colour:
                attrs_out.append(f'color="{_css_colour(colour)}"')

            size = _css_points(style) or _legacy_font_size(a.get("size"))
            if size:
                attrs_out.append(f'size="{size}"')

            weight = re.search(r"font-weight\s*:\s*(bold|[6-9]00)", style, re.I)
            italic = re.search(r"font-style\s*:\s*italic", style, re.I)
            underline = re.search(r"text-decoration[^:]*:\s*[^;]*underline", style, re.I)

            opened = []
            if attrs_out:
                self.buf.append("<font " + " ".join(attrs_out) + ">")
                opened.append("</font>")
            if weight:
                self.buf.append("<b>")
                opened.append("</b>")
            if italic:
                self.buf.append("<i>")
                opened.append("</i>")
            if underline:
                self.buf.append("<u>")
                opened.append("</u>")

            self._span_open = getattr(self, "_span_open", [])
            self._span_open.append(opened)
            return

        if tag == "a":
            href = a.get("href", "")
            if href.startswith(("http://", "https://")):
                self.buf.append(f'<link href="{href}" color="#006499">')
                self._link_open = getattr(self, "_link_open", [])
                self._link_open.append(True)
            else:
                self._link_open = getattr(self, "_link_open", [])
                self._link_open.append(False)
            return

        if tag == "img":
            self._image(a)
            return

        if tag == "hr":
            self._flush()
            self.flow.append(Spacer(1, 4))
            self.flow.append(HRFlowable(width="100%", thickness=0.7,
                                        color=colors.HexColor("#D3D6DD")))
            self.flow.append(Spacer(1, 8))
            return

        if tag in ("ul", "ol"):
            self._flush()
            self._list_stack.append({"kind": tag, "items": []})
            return

        if tag == "li":
            self._flush()
            self.block = "li"
            return

        if tag == "table":
            self._flush()
            self._table = {"rows": [], "row": None, "header": False, "header_rows": 0}
            return

        if tag == "tr" and self._table is not None:
            self._table["row"] = []
            return

        if tag in ("td", "th") and self._table is not None:
            self._flush()
            self.block = "th" if tag == "th" else "td"
            self.align = _align_from(style, a.get("align", ""))
            return

        if tag in _BLOCK_TAGS or tag == "div":
            self._flush()

            # A signature block is a unit: it must not split across a page.
            if not self._in_sig and ("sig-block" in klass or "data-sig-block" in a):
                self._in_sig = True
                self._sig_depth = 1
                self._sig = {"lines": []}
                return

            if self._in_sig and tag == "div":
                self._sig_depth += 1
                # The empty rule div marks where the signature line goes, so
                # "For and on behalf of…" stays above it and the name below,
                # which is the convention every signed letter follows.
                if "sig-block__line" in klass:
                    self._sig["rule_at"] = len(self._sig.get("lines", []))
                    self.block = "sigrole"
                    return
                # The name line carries the weight; the role line is quiet.
                self.block = "signame" if "sig-block__name" in klass else "sigrole"
                return

            self.block = tag if tag in self.st else "p"
            self.align = _align_from(style, a.get("align", ""))
            self.klass = klass
            return

    def handle_endtag(self, tag):
        if tag in _INLINE_MAP:
            self.buf.append(_INLINE_MAP[tag][1])
            return

        if tag in ("span", "font"):
            stack = getattr(self, "_span_open", [])
            if stack:
                for close in reversed(stack.pop()):
                    self.buf.append(close)
            return

        if tag == "a":
            stack = getattr(self, "_link_open", [])
            if stack and stack.pop():
                self.buf.append("</link>")
            return

        if tag in ("ul", "ol"):
            self._flush()
            group = self._list_stack.pop() if self._list_stack else None
            if group and group["items"]:
                flowable = ListFlowable(
                    group["items"],
                    bulletType="1" if group["kind"] == "ol" else "bullet",
                    bulletFontName="Helvetica",
                    bulletFontSize=10.5,
                    bulletOffsetY=-1,
                    leftIndent=7 * mm,
                    bulletColor=colors.HexColor("#00A7E4"),
                )
                target = (
                    self._list_stack[-1]["items"] if self._list_stack else self.flow
                )
                if self._list_stack:
                    target.append(ListItem(flowable))
                else:
                    target.append(flowable)
                    self.flow.append(Spacer(1, 4))
            self.block = "p"
            return

        if tag == "li":
            self._flush()
            self.block = "p"
            return

        if tag in ("td", "th") and self._table is not None:
            self._flush()
            if self._table["row"] is not None and not self._table["row"]:
                self._table["row"].append(Paragraph("", self.st["td"]))
            if self.block == "th":
                self._table["header"] = True
            self.block = "p"
            self.align = None
            return

        if tag == "tr" and self._table is not None:
            row = self._table["row"] or []
            self._table["row"] = None
            if row:
                self._table["rows"].append(row)
                if self._table["header"] and len(self._table["rows"]) == 1:
                    self._table["header_rows"] = 1
                self._table["header"] = False
            return

        if tag == "table":
            self._emit_table()
            return

        if tag in _BLOCK_TAGS or tag == "div":
            self._flush()
            if self._in_sig and tag == "div":
                self._sig_depth -= 1
                if self._sig_depth <= 0:
                    self._emit_signature()
                else:
                    self.block = "sigrole"
                    return
            self.block = "p"
            self.align = None
            self.klass = ""

    def handle_data(self, data):
        if not data:
            return
        if not data.strip() and not self.buf:
            return
        self.buf.append(_esc(data))

    # -- composites -------------------------------------------------------
    def _image(self, attrs: dict):
        src = attrs.get("src", "")
        raw = self._load_image(src)
        if raw is None:
            return

        try:
            reader = io.BytesIO(raw)
            from reportlab.lib.utils import ImageReader

            iw, ih = ImageReader(reader).getSize()
        except Exception as exc:  # unreadable bytes: skip rather than fail the render
            logger.warning(f"Studio: skipping unreadable image ({exc})")
            return

        # data-size maps to the three widths the Studio offers.
        size = (attrs.get("data-size") or "medium").lower()
        fraction = {"small": 0.28, "medium": 0.52, "large": 0.86, "full": 1.0}.get(size, 0.52)

        explicit = attrs.get("width")
        if explicit and str(explicit).rstrip("px").isdigit():
            # The canvas is 210 mm wide at 96 dpi ≈ 794 px, so scale from that.
            target = min(self.width, float(str(explicit).rstrip("px")) / 794.0 * self.width)
        else:
            target = self.width * fraction

        height = target * (ih / iw) if iw else target

        img = RLImage(io.BytesIO(raw), width=target, height=height)
        img.hAlign = {TA_CENTER: "CENTER", TA_RIGHT: "RIGHT"}.get(self.align, "LEFT")

        if self._in_sig:
            self._sig.setdefault("image", img)
        else:
            self._flush()
            self.flow.append(Spacer(1, 4))
            self.flow.append(img)
            self.flow.append(Spacer(1, 8))

    def _load_image(self, src: str) -> Optional[bytes]:
        if not src:
            return None

        if src.startswith("data:"):
            try:
                head, _, payload = src.partition(",")
                if "base64" not in head:
                    return None
                raw = base64.b64decode(payload, validate=False)
            except (binascii.Error, ValueError):
                return None
            if len(raw) > MAX_EMBEDDED_IMAGE_BYTES:
                logger.warning("Studio: embedded image over the size limit, skipped")
                return None
            return raw

        # Everything else must resolve to a file this server owns. Remote URLs
        # are never fetched: a render must not make outbound requests.
        path = self.resolve(src)
        if not path:
            return None
        try:
            data = Path(path).read_bytes()
        except OSError:
            return None
        return data if len(data) <= MAX_EMBEDDED_IMAGE_BYTES else None

    def _emit_table(self):
        table = self._table
        self._table = None
        if not table or not table["rows"]:
            return

        rows = table["rows"]
        cols = max(len(r) for r in rows)
        for r in rows:
            while len(r) < cols:
                r.append(Paragraph("", self.st["td"]))

        col_width = self.width / cols
        t = Table(rows, colWidths=[col_width] * cols, repeatRows=table["header_rows"])

        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D3D6DD")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, table["header_rows"]), (-1, -1),
             [colors.white, colors.HexColor("#FAFAFB")]),
        ]
        if table["header_rows"]:
            style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#006499")))
        t.setStyle(TableStyle(style))

        self.flow.append(Spacer(1, 5))
        self.flow.append(t)
        self.flow.append(Spacer(1, 10))

    def _emit_signature(self):
        sig = self._sig
        self._in_sig = False
        self._sig = {}

        lines = sig.get("lines", [])
        rule_at = sig.get("rule_at")
        if rule_at is None:
            rule_at = 0  # no explicit marker: rule first, then everything

        parts: list = [Spacer(1, 10)]
        parts.extend(lines[:rule_at])          # "For and on behalf of …"

        if sig.get("image"):
            img = sig["image"]
            # A signature is a mark, not an illustration: cap it at 34 mm.
            if img.drawWidth > 34 * mm:
                scale = 34 * mm / img.drawWidth
                img.drawWidth *= scale
                img.drawHeight *= scale
            img.hAlign = "LEFT"
            parts.append(Spacer(1, 3))
            parts.append(img)

        parts.append(HRFlowable(width=58 * mm, thickness=0.8, color=colors.HexColor("#2E3138"),
                                spaceBefore=2, spaceAfter=4, hAlign="LEFT"))
        parts.extend(lines[rule_at:])          # name, role, date
        parts.append(Spacer(1, 8))

        self.flow.append(KeepTogether(parts))


# --------------------------------------------------------------- the chrome


def _fit_logo(png_name: Optional[str], width_mm: float):
    """Load a brand PNG at a given printed width, or None if it is missing."""
    if not png_name:
        return None
    path = BRAND_DIR / png_name
    if not path.exists():
        return None
    try:
        from reportlab.lib.utils import ImageReader

        reader = ImageReader(str(path))
        iw, ih = reader.getSize()
        w = width_mm * mm
        return reader, w, w * (ih / iw)
    except Exception:
        return None


def _paint_chrome(canvas, doc, spec: dict, title: str):
    """
    Draw the letterhead. Runs on every page, so headers, rails, watermarks and
    footers repeat exactly as they do in the canvas.
    """
    page_w, page_h = doc.pagesize
    canvas.saveState()

    header = spec.get("header") or {"kind": "none"}
    kind = header.get("kind", "none")
    h = float(header.get("height", 0)) * mm

    # -- watermark, behind everything -------------------------------------
    wm = spec.get("watermark")
    if wm and wm.get("text"):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor(wm.get("color", "#0A2A3D")))
        canvas.setFillAlpha(float(wm.get("opacity", 0.05)))
        canvas.translate(page_w / 2, page_h / 2)
        canvas.rotate(38)
        size = 96 if len(wm["text"]) <= 8 else 52
        canvas.setFont("Helvetica-Bold", size)
        canvas.drawCentredString(0, -size * 0.35, wm["text"])
        canvas.restoreState()

    # -- side rail --------------------------------------------------------
    rail = spec.get("siderail")
    if rail:
        canvas.setFillColor(colors.HexColor(rail.get("color", "#00A7E4")))
        w = float(rail.get("width", 4)) * mm
        x = 0 if rail.get("side", "left") == "left" else page_w - w
        canvas.rect(x, 0, w, page_h, stroke=0, fill=1)

    # -- header -----------------------------------------------------------
    if kind != "none" and h:
        top = page_h - h
        background = header.get("background", "#FFFFFF")

        if kind in ("band", "tinted"):
            canvas.setFillColor(colors.HexColor(background))
            canvas.rect(0, top, page_w, h, stroke=0, fill=1)

        rule = header.get("rule")
        if rule:
            canvas.setStrokeColor(colors.HexColor(rule))
            canvas.setLineWidth(2.2)
            canvas.line(0, top, page_w, top)

        left = float(spec["page"].get("margin_left", 22)) * mm
        right = page_w - float(spec["page"].get("margin_right", 20)) * mm

        logo_spec = header.get("logo") or {}
        logo = _fit_logo(logo_spec.get("png"), float(header.get("logo_width", 44)))
        text_x = left
        if logo:
            reader, lw, lh = logo
            ly = top + (h - lh) / 2
            canvas.drawImage(reader, left, ly, width=lw, height=lh, mask="auto")
            if kind == "split":
                text_x = left + lw + 8 * mm

        title_text = header.get("title", "")
        subtitle = header.get("subtitle", "")

        if kind == "split":
            if title_text:
                canvas.setFillColor(colors.HexColor(header.get("title_color", "#16181D")))
                canvas.setFont("Helvetica-Bold", 10)
                canvas.drawRightString(right, top + h / 2 + 1, title_text)
            if subtitle:
                canvas.setFillColor(colors.HexColor(header.get("subtitle_color", "#6B707A")))
                canvas.setFont("Helvetica", 7.5)
                canvas.drawRightString(right, top + h / 2 - 9, subtitle)
        else:
            if title_text:
                canvas.setFillColor(colors.HexColor(header.get("title_color", "#FFFFFF")))
                canvas.setFont("Helvetica-Bold", 11)
                canvas.drawRightString(right, top + h / 2 + 2, title_text)
            if subtitle:
                canvas.setFillColor(colors.HexColor(header.get("subtitle_color", "#FFFFFF")))
                canvas.setFont("Helvetica", 7)
                canvas.drawRightString(right, top + h / 2 - 8, subtitle)

    # -- footer -----------------------------------------------------------
    footer = spec.get("footer") or {}
    lines = footer.get("lines") or []
    fkind = footer.get("kind", "page-number")
    left = float(spec["page"].get("margin_left", 22)) * mm
    right = page_w - float(spec["page"].get("margin_right", 20)) * mm
    base = 12 * mm

    if fkind == "band" and lines:
        band_h = 14 * mm
        canvas.setFillColor(colors.HexColor(footer.get("background", "#00559B")))
        canvas.rect(0, 0, page_w, band_h, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor(footer.get("color", "#FFFFFF")))
        canvas.setFont("Helvetica", 6.8)
        y = band_h - 5.5 * mm
        for line in lines[:2]:
            canvas.drawString(left, y, line)
            y -= 3.6 * mm
        canvas.drawRightString(right, band_h / 2 - 1, f"Page {canvas.getPageNumber()}")
    else:
        if fkind == "rule":
            canvas.setStrokeColor(colors.HexColor(footer.get("rule", "#E6E8EC")))
            canvas.setLineWidth(0.7)
            canvas.line(left, base + 6 * mm, right, base + 6 * mm)
        canvas.setFillColor(colors.HexColor(footer.get("color", "#6B707A")))
        canvas.setFont("Helvetica", 6.8)
        y = base + 2 * mm
        for line in lines[:2]:
            canvas.drawString(left, y, line)
            y -= 3.4 * mm
        if footer.get("page_numbers", True):
            canvas.drawRightString(right, base + 2 * mm, f"Page {canvas.getPageNumber()}")

    canvas.restoreState()


# ------------------------------------------------------------------- render


def render_pdf(
    html: str,
    template_id: Optional[str] = None,
    title: str = "Document",
    author: str = "",
    subject: str = "",
    asset_resolver=None,
) -> bytes:
    """
    Render a composed document to PDF bytes.

    `asset_resolver` maps an `<img src>` the browser used to an absolute path on
    this server. Anything it declines to resolve is dropped, which is what keeps
    a body from pulling in files it was never granted.
    """
    spec = get_template(template_id)
    page = spec["page"]

    clean = sanitize_html(html)

    buffer = io.BytesIO()
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        title=title or "Document",
        author=author or "HARMAN Document Management System",
        subject=subject or spec.get("name", ""),
        creator="HARMAN DMS",
        leftMargin=page["margin_left"] * mm,
        rightMargin=page["margin_right"] * mm,
        topMargin=page["margin_top"] * mm,
        bottomMargin=page["margin_bottom"] * mm,
    )

    frame = Frame(
        doc.leftMargin, doc.bottomMargin,
        doc.width, doc.height,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        id="body",
    )
    doc.addPageTemplates([
        PageTemplate(
            id="letterhead",
            frames=[frame],
            onPage=lambda c, d: _paint_chrome(c, d, spec, title),
        )
    ])

    parser = _Blocks(_styles(spec), doc.width, asset_resolver)
    try:
        parser.feed(clean)
        parser.close()
    except Exception as exc:
        raise RenderError(f"Could not read the document body: {exc}") from exc

    parser._flush()
    story = parser.flow

    if not story:
        story = [Paragraph("This document is empty.", _styles(spec)["meta"])]

    try:
        doc.build(story)
    except Exception as exc:
        logger.exception("PDF build failed")
        raise RenderError(f"Could not lay the document out: {exc}") from exc

    return buffer.getvalue()


def page_estimate(html: str) -> int:
    """Rough page count for the status bar. Cheap, and never claims precision."""
    text = html_to_text(html)
    return max(1, round(len(text) / 2600 + 0.4))
