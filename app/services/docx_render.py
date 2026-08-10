"""
Write a .docx from the same sanitised HTML the PDF renderer reads.

A .docx is a zip of XML parts, and the subset needed for a business document -
headings, paragraphs, runs with bold/italic/underline, lists and tables - is
small enough to emit directly. Doing it with the standard library rather than
another dependency keeps the deployment story unchanged, and means the export
can never disagree with the PDF about what the document says: both walk the
same HTML.

Not supported, deliberately: images and the letterhead. Word has no notion of
the page furniture ReportLab paints, and a .docx that silently dropped the
letterhead while looking otherwise identical would mislead. The letterhead
lives in the PDF; the .docx is the editable text.
"""
from __future__ import annotations

import re
import zipfile
from html.parser import HTMLParser
from io import BytesIO
from typing import Optional

from .pdf_render import sanitize_html

XML_HEADER = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

CONTENT_TYPES = XML_HEADER + """<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

ROOT_RELS = XML_HEADER + """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

DOC_RELS = XML_HEADER + """<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

# Heading and body styles matching the on-screen and PDF hierarchy.
STYLES = XML_HEADER + """<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:cs="Calibri"/>
<w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal">
<w:name w:val="Normal"/><w:pPr><w:spacing w:after="140" w:line="276" w:lineRule="auto"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Title">
<w:name w:val="Title"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="120" w:after="200"/></w:pPr>
<w:rPr><w:b/><w:color w:val="006499"/><w:sz w:val="34"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1">
<w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:pPr><w:outlineLvl w:val="0"/><w:spacing w:before="240" w:after="120"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="26"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2">
<w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
<w:pPr><w:outlineLvl w:val="1"/><w:spacing w:before="200" w:after="90"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="23"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Quiet">
<w:name w:val="Quiet"/><w:basedOn w:val="Normal"/>
<w:rPr><w:color w:val="6B707A"/><w:sz w:val="18"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph">
<w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>
<w:pPr><w:ind w:left="720"/><w:spacing w:after="60"/></w:pPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>
<w:tblPr><w:tblBorders>
<w:top w:val="single" w:sz="4" w:color="D3D6DD"/><w:left w:val="single" w:sz="4" w:color="D3D6DD"/>
<w:bottom w:val="single" w:sz="4" w:color="D3D6DD"/><w:right w:val="single" w:sz="4" w:color="D3D6DD"/>
<w:insideH w:val="single" w:sz="4" w:color="D3D6DD"/><w:insideV w:val="single" w:sz="4" w:color="D3D6DD"/>
</w:tblBorders></w:tblPr></w:style>
</w:styles>"""


def _esc(text: str) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;")
    )


class _Docx(HTMLParser):
    """Walk sanitised HTML and emit WordprocessingML body content."""

    HEADINGS = {"h1": "Title", "h2": "Heading1", "h3": "Heading2", "h4": "Heading2"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.runs: list[str] = []
        self.style = "Normal"
        self.bold = 0
        self.italic = 0
        self.underline = 0
        self.list_depth = 0
        self.ordered = False
        self.li_number = 0
        self._table: Optional[dict] = None
        self._in_sig = False

    # -- runs -------------------------------------------------------------
    def _run(self, text: str) -> str:
        props = []
        if self.bold:
            props.append("<w:b/>")
        if self.italic:
            props.append("<w:i/>")
        if self.underline:
            props.append("<w:u w:val='single'/>")
        rpr = f"<w:rPr>{''.join(props)}</w:rPr>" if props else ""
        return f'<w:r>{rpr}<w:t xml:space="preserve">{_esc(text)}</w:t></w:r>'

    def _flush(self, style: Optional[str] = None):
        if not self.runs:
            return
        body = "".join(self.runs)
        self.runs = []
        use = style or self.style

        indent = ""
        if self.list_depth:
            use = "ListParagraph"
            marker = f"{self.li_number}." if self.ordered else "•"
            body = self._run(f"{marker}  ") + body
            indent = "<w:ind w:left='567'/>"

        paragraph = f'<w:p><w:pPr><w:pStyle w:val="{use}"/>{indent}</w:pPr>{body}</w:p>'

        if self._table is not None and self._table["cell"] is not None:
            self._table["cell"].append(paragraph)
        else:
            self.out.append(paragraph)

    # -- tags -------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)

        if tag in ("strong", "b"):
            self.bold += 1
        elif tag in ("em", "i"):
            self.italic += 1
        elif tag == "u":
            self.underline += 1
        elif tag == "br":
            self.runs.append("<w:r><w:br/></w:r>")
        elif tag in self.HEADINGS:
            self._flush()
            self.style = self.HEADINGS[tag]
        elif tag in ("p", "div", "blockquote"):
            self._flush()
            klass = a.get("class", "")
            if "sig-block" in klass:
                self._in_sig = True
                self.out.append(_spacer())
            self.style = "Quiet" if ("doc-meta" in klass or self._in_sig) else "Normal"
        elif tag in ("ul", "ol"):
            self._flush()
            self.list_depth += 1
            self.ordered = tag == "ol"
            self.li_number = 0
        elif tag == "li":
            self._flush()
            self.li_number += 1
        elif tag == "hr":
            self._flush()
            self.out.append(
                '<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="6" '
                'w:color="D3D6DD"/></w:pBdr></w:pPr></w:p>'
            )
        elif tag == "table":
            self._flush()
            self._table = {"rows": [], "row": None, "cell": None, "header": False}
        elif tag == "tr" and self._table is not None:
            self._table["row"] = []
        elif tag in ("td", "th") and self._table is not None:
            self._flush()
            self._table["cell"] = []
            if tag == "th":
                self.bold += 1
                self._table["header"] = True

    def handle_endtag(self, tag):
        if tag in ("strong", "b"):
            self.bold = max(0, self.bold - 1)
        elif tag in ("em", "i"):
            self.italic = max(0, self.italic - 1)
        elif tag == "u":
            self.underline = max(0, self.underline - 1)
        elif tag in self.HEADINGS:
            self._flush()
            self.style = "Normal"
        elif tag in ("p", "div", "blockquote"):
            self._flush()
            if tag == "div" and self._in_sig:
                self._in_sig = False
            self.style = "Normal"
        elif tag in ("ul", "ol"):
            self._flush()
            self.list_depth = max(0, self.list_depth - 1)
        elif tag == "li":
            self._flush()
        elif tag in ("td", "th") and self._table is not None:
            self._flush()
            if tag == "th":
                self.bold = max(0, self.bold - 1)
            cell = self._table["cell"] or ["<w:p/>"]
            self._table["cell"] = None
            shading = ('<w:shd w:val="clear" w:fill="006499"/>'
                       if tag == "th" else "")
            if self._table["row"] is not None:
                self._table["row"].append(
                    f'<w:tc><w:tcPr>{shading}</w:tcPr>{"".join(cell)}</w:tc>'
                )
        elif tag == "tr" and self._table is not None:
            row = self._table["row"] or []
            self._table["row"] = None
            if row:
                self._table["rows"].append(f'<w:tr>{"".join(row)}</w:tr>')
        elif tag == "table":
            self._emit_table()

    def handle_data(self, data):
        if not data or (not data.strip() and not self.runs):
            return
        self.runs.append(self._run(data))

    def _emit_table(self):
        table = self._table
        self._table = None
        if not table or not table["rows"]:
            return
        self.out.append(
            '<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
            '<w:tblW w:w="5000" w:type="pct"/>'
            '<w:tblBorders>'
            '<w:top w:val="single" w:sz="4" w:color="D3D6DD"/>'
            '<w:left w:val="single" w:sz="4" w:color="D3D6DD"/>'
            '<w:bottom w:val="single" w:sz="4" w:color="D3D6DD"/>'
            '<w:right w:val="single" w:sz="4" w:color="D3D6DD"/>'
            '<w:insideH w:val="single" w:sz="4" w:color="D3D6DD"/>'
            '<w:insideV w:val="single" w:sz="4" w:color="D3D6DD"/>'
            '</w:tblBorders></w:tblPr>'
            + "".join(table["rows"]) + "</w:tbl>" + _spacer()
        )

    def finish(self) -> str:
        self._flush()
        return "".join(self.out) or "<w:p/>"


def _spacer() -> str:
    return '<w:p><w:pPr><w:spacing w:after="80"/></w:pPr></w:p>'


def render_docx(
    html: str,
    title: str = "Document",
    author: str = "",
    subtitle: str = "",
) -> bytes:
    """Render sanitised HTML to .docx bytes."""
    parser = _Docx()
    parser.feed(sanitize_html(html or ""))
    parser.close()
    body = parser.finish()

    header = ""
    if subtitle:
        header = (
            f'<w:p><w:pPr><w:pStyle w:val="Quiet"/></w:pPr>'
            f'<w:r><w:t xml:space="preserve">{_esc(subtitle)}</w:t></w:r></w:p>'
        )

    document = XML_HEADER + (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{header}{body}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
        '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/>'
        "</w:sectPr></w:body></w:document>"
    )

    core = XML_HEADER + (
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f"<dc:title>{_esc(title)}</dc:title>"
        f"<dc:creator>{_esc(author or 'HARMAN DMS')}</dc:creator>"
        f"<cp:lastModifiedBy>{_esc(author or 'HARMAN DMS')}</cp:lastModifiedBy>"
        "</cp:coreProperties>"
    )

    app = XML_HEADER + (
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
        "<Application>HARMAN Document Management System</Application>"
        "</Properties>"
    )

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("docProps/core.xml", core)
        z.writestr("docProps/app.xml", app)

    return buffer.getvalue()


def html_to_plain(html: str, title: str = "") -> str:
    """A .txt export: the words, with structure preserved as indentation."""
    from .pdf_render import html_to_text

    body = html_to_text(html or "")
    if not title:
        return body
    rule = "=" * min(72, max(24, len(title)))
    return f"{title}\n{rule}\n\n{body}\n"
