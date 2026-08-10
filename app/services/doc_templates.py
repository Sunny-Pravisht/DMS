"""
Document templates: the letterhead a composed document is printed on.

There is exactly one definition of a template and it lives here. The Studio
canvas renders the header, side rail, watermark and footer from this spec, and
so does the PDF renderer. Change a colour once and both follow, which is the
only way "what I saw is what I got" survives contact with a second renderer.

A template describes the *paper*, never the words. Body content is the user's,
carried separately as sanitised HTML. `starter` is only the first draft handed
to someone who picked the template on a blank page.

Measurements are millimetres, because that is how paper is specified and how
ReportLab's mm unit works. The browser uses the same numbers via CSS mm.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Optional

# Web path for the brand marks; the PDF renderer maps this to a PNG on disk.
BRAND_WEB = "/static/ui/assets/brand"
BRAND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "ui" / "assets" / "brand"


def _logo(key: str) -> dict:
    """
    A mark, addressable by both renderers.

    The browser gets an SVG where one exists, because it stays crisp at any
    zoom. Real supplied artwork - the HARMAN logo - is a raster, so those keys
    resolve to the PNG instead. Checking the file rather than hard-coding the
    extension means dropping in a new logo needs no code change.

    `web` is what the canvas loads; `png` is what ReportLab embeds, since it
    cannot read SVG at all.
    """
    svg = BRAND_DIR / f"{key}.svg"
    web = f"{BRAND_WEB}/{key}.svg" if svg.exists() else f"{BRAND_WEB}/{key}.png"
    return {"key": key, "web": web, "png": f"{key}.png"}


A4 = {"width": 210, "height": 297}


TEMPLATES: list[dict] = [
    # ---------------------------------------------------------------- blank
    {
        "id": "blank",
        "name": "Blank document",
        "org": "",
        "category": "General",
        "description": "No letterhead. A clean sheet for notes, minutes and internal drafts.",
        "accent": "#00A7E4",
        "ink": "#16181D",
        "page": dict(A4, margin_top=25, margin_bottom=22, margin_left=22, margin_right=22),
        "header": {"kind": "none"},
        "siderail": None,
        "footer": {"kind": "page-number", "lines": [], "page_numbers": True},
        "watermark": None,
        "meta": {"department": "", "doctype": ""},
        # Genuinely empty. Blank means blank: prompt text placed as real content
        # has to be selected and deleted before anything can be written, and it
        # gets published verbatim by anyone who does not notice it. The editor
        # shows the same invitation as a placeholder instead, which cannot be
        # saved by accident.
        "starter": [],
    },

    # ------------------------------------------------------ HARMAN official
    {
        "id": "harman-letterhead",
        "name": "HARMAN official letterhead",
        "org": "HARMAN International",
        "category": "Company",
        "description": "The corporate letterhead: blue masthead, brand rail and the "
                       "registered-office footer. Use for anything that leaves the plant.",
        "accent": "#00A7E4",
        "accent_dark": "#006499",
        "ink": "#0A2A3D",
        "page": dict(A4, margin_top=40, margin_bottom=26, margin_left=26, margin_right=20),
        "header": {
            "kind": "band",
            "height": 30,
            "background": "#0A2A3D",
            # Filled mastheads take the reversed lockup: the standard wordmark
            # is navy, and navy on navy is nothing at all.
            "logo": _logo("harman-white"),
            "logo_width": 46,
            "title": "",
            "subtitle": "CONNECTED TECHNOLOGIES  ·  DOCUMENT CONTROL",
            "subtitle_color": "#7FD6F4",
            "rule": "#00A7E4",
        },
        "siderail": {"width": 4, "color": "#00A7E4", "side": "left"},
        "footer": {
            "kind": "rule",
            "rule": "#E6E8EC",
            "lines": [
                "HARMAN International Industries, Incorporated  ·  Manufacturing & Quality",
                "Plot 30-A, Electronic City Phase II, Bengaluru 560100, India  ·  harman.com",
            ],
            "page_numbers": True,
            "color": "#6B707A",
        },
        "watermark": {"kind": "text", "text": "HARMAN", "opacity": 0.045, "color": "#0A2A3D"},
        "meta": {"department": "Operations", "doctype": "Letter"},
        "starter": [
            {"type": "h1", "text": "Subject of this letter"},
            {"type": "meta", "text": "Reference: HAR/DOC/2026/0001    ·    Date: {today}"},
            {"type": "p", "text": "Dear Sir or Madam,"},
            {"type": "p", "text": "Replace this paragraph with the body of your letter. "
                                  "Everything on this page except the letterhead is yours to edit."},
            {"type": "p", "text": "Yours faithfully,"},
            {"type": "signature", "text": "For and on behalf of HARMAN International"},
        ],
    },

    # -------------------------------------------------------- Maruti Suzuki
    {
        "id": "maruti-suzuki",
        "name": "Maruti Suzuki vendor letterhead",
        "org": "Maruti Suzuki India Limited",
        "category": "Vendor",
        "description": "For correspondence issued to or on behalf of Maruti Suzuki: "
                       "purchase orders, supply schedules and quality correspondence.",
        "accent": "#00559B",
        "accent_dark": "#00417A",
        "ink": "#12233A",
        "page": dict(A4, margin_top=38, margin_bottom=26, margin_left=22, margin_right=20),
        "header": {
            "kind": "split",
            "height": 28,
            "background": "#FFFFFF",
            "logo": _logo("maruti-suzuki"),
            "logo_width": 48,
            "title": "MARUTI SUZUKI INDIA LIMITED",
            "subtitle": "Vendor correspondence  ·  Supplier quality",
            "title_color": "#00559B",
            "subtitle_color": "#6B707A",
            "rule": "#E01E26",
        },
        "siderail": None,
        "footer": {
            "kind": "band",
            "background": "#00559B",
            "lines": [
                "Maruti Suzuki India Limited  ·  Plot 1, Nelson Mandela Road, Vasant Kunj, New Delhi 110070",
                "Issued through HARMAN Document Management System",
            ],
            "page_numbers": True,
            "color": "#FFFFFF",
        },
        "watermark": None,
        "meta": {"department": "Procurement", "doctype": "Purchase order"},
        "starter": [
            {"type": "h1", "text": "Purchase order"},
            {"type": "meta", "text": "PO number: MSIL/PO/2026/0001    ·    Date: {today}"},
            {"type": "p", "text": "To the supplier named above: this order is placed under the "
                                  "terms of the master supply agreement in force."},
            {"type": "table", "text": "Line|Description|Quantity|Unit price\n1|Item description|0|0.00"},
            {"type": "signature", "text": "Authorised signatory, Procurement"},
        ],
    },

    # ------------------------------------------------------------- Mahindra
    {
        "id": "mahindra",
        "name": "Mahindra vendor letterhead",
        "org": "Mahindra & Mahindra Limited",
        "category": "Vendor",
        "description": "Mahindra-facing paperwork: delivery notes, inspection reports and "
                       "goods-receipt correspondence.",
        "accent": "#C8102E",
        "accent_dark": "#96001F",
        "ink": "#1B1B1B",
        "page": dict(A4, margin_top=38, margin_bottom=26, margin_left=24, margin_right=20),
        "header": {
            "kind": "split",
            "height": 28,
            "background": "#FFFFFF",
            "logo": _logo("mahindra"),
            "logo_width": 44,
            "title": "MAHINDRA & MAHINDRA LIMITED",
            "subtitle": "Automotive division  ·  Supplier documentation",
            "title_color": "#C8102E",
            "subtitle_color": "#5B6770",
            "rule": "#C8102E",
        },
        "siderail": {"width": 4, "color": "#C8102E", "side": "right"},
        "footer": {
            "kind": "rule",
            "rule": "#E6E8EC",
            "lines": [
                "Mahindra & Mahindra Limited  ·  Mahindra Towers, Worli, Mumbai 400018",
                "Issued through HARMAN Document Management System",
            ],
            "page_numbers": True,
            "color": "#6B707A",
        },
        "watermark": None,
        "meta": {"department": "Operations", "doctype": "Delivery note"},
        "starter": [
            {"type": "h1", "text": "Delivery note"},
            {"type": "meta", "text": "Consignment: MM/DN/2026/0001    ·    Date: {today}"},
            {"type": "p", "text": "The goods listed below were despatched against the referenced order."},
            {"type": "table", "text": "Item|Part number|Quantity|Batch\n1|PN-00000|0|—"},
            {"type": "signature", "text": "Despatched by, Operations"},
        ],
    },

    # ----------------------------------------------------------------- Tata
    {
        "id": "tata",
        "name": "Tata vendor letterhead",
        "org": "Tata Motors Limited",
        "category": "Vendor",
        "description": "Tata-facing paperwork: contracts, service agreements and "
                       "commercial correspondence.",
        "accent": "#486AAE",
        "accent_dark": "#2E4A85",
        "ink": "#14213D",
        "page": dict(A4, margin_top=40, margin_bottom=26, margin_left=24, margin_right=20),
        "header": {
            "kind": "band",
            "height": 28,
            "background": "#486AAE",
            "logo": _logo("tata-white"),
            "logo_width": 42,
            "title": "",
            "subtitle": "TATA MOTORS  ·  COMMERCIAL DOCUMENTATION",
            "subtitle_color": "#DCE5F5",
            "rule": "#2E4A85",
        },
        "siderail": None,
        "footer": {
            "kind": "rule",
            "rule": "#E6E8EC",
            "lines": [
                "Tata Motors Limited  ·  Bombay House, 24 Homi Mody Street, Mumbai 400001",
                "Issued through HARMAN Document Management System",
            ],
            "page_numbers": True,
            "color": "#6B707A",
        },
        "watermark": {"kind": "text", "text": "TATA", "opacity": 0.04, "color": "#486AAE"},
        "meta": {"department": "Legal", "doctype": "Contract"},
        "starter": [
            {"type": "h1", "text": "Agreement"},
            {"type": "meta", "text": "Agreement number: TML/AGR/2026/0001    ·    Date: {today}"},
            {"type": "h2", "text": "1. Parties"},
            {"type": "p", "text": "This agreement is made between the parties named below."},
            {"type": "h2", "text": "2. Scope"},
            {"type": "p", "text": "Describe the scope of the agreement here."},
            {"type": "signature", "text": "For and on behalf of the parties"},
        ],
    },

    # ------------------------------------------- HARMAN internal quality memo
    {
        "id": "harman-quality",
        "name": "HARMAN quality report",
        "org": "HARMAN International",
        "category": "Company",
        "description": "Plant-floor report layout: tinted masthead, controlled-document "
                       "footer and a 'Controlled copy' watermark.",
        "accent": "#006499",
        "accent_dark": "#004B73",
        "ink": "#16181D",
        "page": dict(A4, margin_top=36, margin_bottom=26, margin_left=22, margin_right=20),
        "header": {
            "kind": "tinted",
            "height": 26,
            "background": "#E6F7FD",
            "logo": _logo("harman"),
            "logo_width": 40,
            "title": "QUALITY & MANUFACTURING REPORT",
            "subtitle": "Controlled document  ·  ISO 9001 : 2015",
            "title_color": "#006499",
            "subtitle_color": "#4B5058",
            "rule": "#00A7E4",
        },
        "siderail": {"width": 3, "color": "#00A7E4", "side": "left"},
        "footer": {
            "kind": "rule",
            "rule": "#E6E8EC",
            "lines": [
                "Controlled document  ·  Uncontrolled once printed  ·  HARMAN Document Management System",
            ],
            "page_numbers": True,
            "color": "#6B707A",
        },
        "watermark": {"kind": "text", "text": "CONTROLLED COPY", "opacity": 0.05, "color": "#006499"},
        "meta": {"department": "Compliance & Internal Audit", "doctype": "Quality report"},
        "starter": [
            {"type": "h1", "text": "Quality inspection report"},
            {"type": "meta", "text": "Report number: HAR/QA/2026/0001    ·    Date: {today}"},
            {"type": "h2", "text": "Scope of inspection"},
            {"type": "p", "text": "Describe the batch, line and standard applied."},
            {"type": "h2", "text": "Findings"},
            {"type": "table", "text": "Check|Specification|Measured|Result\n1|—|—|Pass"},
            {"type": "h2", "text": "Disposition"},
            {"type": "p", "text": "State the disposition and any corrective action raised."},
            {"type": "signature", "text": "Quality engineer"},
        ],
    },
]


_BY_ID = {t["id"]: t for t in TEMPLATES}

DEFAULT_TEMPLATE_ID = "blank"


def all_templates() -> list[dict]:
    """Every template, safe to hand to the API layer."""
    return [deepcopy(t) for t in TEMPLATES]


def get_template(template_id: Optional[str]) -> dict:
    """A template by id, falling back to blank rather than failing a render."""
    return deepcopy(_BY_ID.get(template_id or "", _BY_ID[DEFAULT_TEMPLATE_ID]))


def exists(template_id: Optional[str]) -> bool:
    return template_id in _BY_ID


def starter_html(template_id: str, today: str) -> str:
    """
    The first draft handed to someone who picks this template on a blank page.

    Rendered here rather than in the browser so the starter content and the
    letterhead can never drift apart.
    """
    tpl = get_template(template_id)
    out: list[str] = []

    for block in tpl.get("starter", []):
        kind = block.get("type")
        text = (block.get("text") or "").replace("{today}", today)

        if kind in ("h1", "h2", "h3"):
            out.append(f"<{kind}>{_esc(text)}</{kind}>")
        elif kind == "meta":
            out.append(f'<p class="doc-meta">{_esc(text)}</p>')
        elif kind == "table":
            out.append(_starter_table(text))
        elif kind == "signature":
            out.append(
                '<div class="sig-block" data-sig-block>'
                '<div class="sig-block__line"></div>'
                f'<div class="sig-block__role">{_esc(text)}</div>'
                '</div>'
            )
        else:
            out.append(f"<p>{_esc(text)}</p>")

    return "\n".join(out)


def _starter_table(text: str) -> str:
    rows = [r.split("|") for r in text.split("\n") if r.strip()]
    if not rows:
        return ""
    head = "".join(f"<th>{_esc(c)}</th>" for c in rows[0])
    body = "".join(
        "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in row) + "</tr>" for row in rows[1:]
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
