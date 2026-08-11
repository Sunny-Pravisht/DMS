#!/usr/bin/env python3
"""
Extract user-visible text from the front end, with file:line for every string.

Used to drive a spell/grammar pass. Deliberately conservative about what counts
as user-visible:

  HTML  text nodes outside <script>/<style>, plus the attributes a user can
        actually read (placeholder, title, aria-label, alt, value on buttons).
  JS    string literals that look like prose - they contain a space, start with
        a letter, and are not selectors, URLs, class lists or format strings.

Comments are ignored: they are developer-facing, and rewriting them would be
churn in files this task is meant to leave functionally untouched.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

UI = Path("frontend/ui")

# Attributes whose value is read by a human.
TEXT_ATTRS = ("placeholder", "title", "aria-label", "alt", "aria-placeholder")

SCRIPT_STYLE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")
ATTR = re.compile(
    r'\b(' + "|".join(TEXT_ATTRS) + r')\s*=\s*"([^"]*)"', re.I
)
# A JS string literal: single or double quoted, no newline.
JS_STR = re.compile(r"""(['"])((?:(?!\1)[^\\\n]|\\.)*)\1""")

# Things that are code, not prose.
NOT_PROSE = re.compile(
    r"""^(?:
          [.#\[]                     # css selector
        | https?:/ | / | \.\. | data: | mailto:
        | [a-z]+(?:-[a-z0-9]+)+$     # kebab-case token / class name
        | [A-Za-z0-9_]+$             # single identifier
        | \s*$
    )""",
    re.X,
)


def html_strings(path: Path):
    raw = path.read_text(encoding="utf-8")
    # Blank out script/style bodies but keep the line count intact.
    masked = SCRIPT_STYLE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), raw)

    for lineno, line in enumerate(masked.splitlines(), 1):
        for m in ATTR.finditer(line):
            value = m.group(2).strip()
            if value and not NOT_PROSE.match(value):
                yield lineno, f"@{m.group(1)}", value
        # Text nodes: whatever survives once tags are removed.
        for chunk in TAG.sub("\n", line).splitlines():
            text = chunk.strip()
            if text and not NOT_PROSE.match(text):
                yield lineno, "text", text


def js_strings(path: Path):
    raw = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(raw.splitlines(), 1):
        stripped = line.lstrip()
        # Skip comment-only lines; block-comment bodies rarely hold quotes we care about.
        if stripped.startswith(("//", "*", "/*")):
            continue
        for m in JS_STR.finditer(line):
            value = m.group(2).strip()
            if len(value) < 4 or " " not in value:
                continue
            if NOT_PROSE.match(value):
                continue
            if not value[0].isalpha():
                continue
            # HTML fragments built in JS still carry prose; strip the tags.
            value = TAG.sub(" ", value)
            value = re.sub(r"\s+", " ", value).strip()
            if value and " " in value:
                yield lineno, "js", value


def main() -> int:
    rows = []
    for path in sorted(UI.rglob("*.html")):
        for lineno, kind, text in html_strings(path):
            rows.append({"file": str(path), "line": lineno, "kind": kind, "text": text})
    for path in sorted(UI.rglob("*.js")):
        for lineno, kind, text in js_strings(path):
            rows.append({"file": str(path), "line": lineno, "kind": kind, "text": text})

    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/ui_text.json")
    out.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    print(f"{len(rows)} strings from "
          f"{len({r['file'] for r in rows})} files -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
