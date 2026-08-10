"""
"Edit with AI": the model acting on the text the author is looking at.

This is deliberately separate from `ai_service.extract_document_metadata`. That
one reads a finished document and reports on it. This one *writes*, so it needs
different guardrails: it must return the document and nothing else - no preamble,
no apology, no commentary - or the editor would paste the model's manners into
the letter.

Everything the model returns is run through the same sanitiser the PDF renderer
uses, so a prompt-injected `<script>` in a source document cannot come back as
markup the browser would run.
"""
from __future__ import annotations

import re
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from .ai_service import AIService
from .pdf_render import sanitize_html

# The subset the model may emit. Kept small on purpose: the letterhead owns the
# look, so the model only supplies structure.
_FORMAT_RULE = (
    "Reply with the document body only, as simple HTML using nothing but "
    "<h2>, <h3>, <p>, <ul>, <ol>, <li>, <strong>, <em> and <br>. "
    "No <html>, <head>, <body>, <style>, <script> or markdown fences. "
    "Do not introduce your answer, do not explain what you changed, do not add "
    "a closing remark. Output the document text and nothing else."
)

# Correction-shaped actions return the author's document with something fixed.
# They must not add structure that was not there: a proofread that silently
# grows a heading is not a proofread, and the author has to notice and undo it.
_NO_NEW_STRUCTURE = (
    "Return only the content that was given to you, corrected. Do not add a "
    "heading, a title, a preamble, a sign-off or any section that is not "
    "already in the source. Do not restate the document's title."
)

ACTIONS: dict[str, dict] = {
    "summarize": {
        "label": "Summarise",
        "system": "You are an editor working inside a corporate document management system.",
        "prompt": "Summarise the document below for a busy approver. Lead with the decision or "
                  "request being made, then the three to six facts that matter most. Keep every "
                  "figure, date, party and reference number exactly as written. Never invent a "
                  "detail that is not in the source.",
        "replaces": False,
    },
    "regenerate": {
        "label": "Rewrite",
        "system": "You are an editor working inside a corporate document management system.",
        "prompt": "Rewrite the document below so it reads clearly and professionally. Keep the "
                  "same meaning, the same facts, the same figures and the same structure of "
                  "sections. Improve sentence flow and remove repetition. Do not add new claims, "
                  "commitments or numbers.",
        "replaces": True,
        "keep_structure": True,
    },
    "grammar": {
        "label": "Fix grammar & spelling",
        "system": "You are a proofreader. You correct; you do not rewrite.",
        "prompt": "Correct the spelling, grammar, punctuation and capitalisation in the document "
                  "below. Preserve the author's wording and tone wherever it is already correct. "
                  "Do not restructure sentences that are merely plain, and do not change any "
                  "figure, date, name or reference.",
        "replaces": True,
        "keep_structure": True,
    },
    "formal": {
        "label": "Make it formal",
        "system": "You are an editor working inside a corporate document management system.",
        "prompt": "Rewrite the document below in formal business English suitable for external "
                  "correspondence with a customer or a supplier. Keep every fact unchanged.",
        "replaces": True,
        "keep_structure": True,
    },
    "concise": {
        "label": "Make it concise",
        "system": "You are an editor working inside a corporate document management system.",
        "prompt": "Tighten the document below. Remove padding, redundancy and throat-clearing. "
                  "Aim for roughly half the length while keeping every fact, figure and "
                  "obligation. Do not drop a requirement to save words.",
        "replaces": True,
        "keep_structure": True,
    },
    "expand": {
        "label": "Expand",
        "system": "You are an editor working inside a corporate document management system.",
        "prompt": "Develop the document below into a fuller draft: keep the author's points and "
                  "add the structure, headings and connective explanation a reader would expect. "
                  "Where a detail is genuinely missing, leave a clearly marked placeholder in "
                  "square brackets rather than inventing it.",
        "replaces": True,
    },
    "bullets": {
        "label": "Convert to bullet points",
        "system": "You are an editor working inside a corporate document management system.",
        "prompt": "Restructure the document below as scannable bullet points grouped under short "
                  "headings. Keep every fact.",
        "replaces": True,
    },
    "continue": {
        "label": "Continue writing",
        "system": "You are an editor working inside a corporate document management system.",
        "prompt": "Continue the document below from where it stops, in the same voice, format "
                  "and level of detail. Write the next two or three paragraphs only. Do not "
                  "repeat what is already written and do not summarise it.",
        "replaces": False,
    },
    "translate": {
        "label": "Translate",
        "system": "You are a professional translator of business and technical documents.",
        "prompt": "Translate the document below into {target}. Keep the structure, the headings "
                  "and every number, date, product code and proper name exactly as they are.",
        "replaces": True,
        "keep_structure": True,
    },
    "draft": {
        "label": "Draft this for me",
        "system": "You are a business writer inside a manufacturing company's document system.",
        "prompt": "Write a complete, ready-to-send document for the request below. Use headings "
                  "and short paragraphs. Where a specific figure, date or name is needed but was "
                  "not supplied, leave a placeholder in square brackets such as [amount] so the "
                  "author can fill it in. Do not invent commitments.",
        "replaces": True,
    },
    "custom": {
        "label": "Custom instruction",
        "system": "You are an editor working inside a corporate document management system.",
        "prompt": "Apply the following instruction to the document below. Keep every fact, "
                  "figure and name unchanged unless the instruction explicitly asks otherwise.\n"
                  "Instruction: {instruction}",
        "replaces": True,
    },
}

# Enough context to work with, short enough to stay inside a free-tier budget.
MAX_INPUT_CHARS = 24_000


class AuthoringError(RuntimeError):
    """The model could not be reached, or returned nothing usable."""


def available_actions() -> list[dict]:
    """What the Studio should offer, described for the UI."""
    return [
        {
            "id": key,
            "label": cfg["label"],
            "replaces": cfg["replaces"],
            "needs_instruction": key in ("custom", "draft"),
            "needs_target": key == "translate",
        }
        for key, cfg in ACTIONS.items()
    ]


def run(
    db: Session,
    action: str,
    text: str,
    instruction: Optional[str] = None,
    target: Optional[str] = None,
    title: Optional[str] = None,
    context: Optional[str] = None,
) -> dict:
    """
    Run one authoring action and return `{html, text, replaces, action}`.

    `text` is the selection when the author highlighted something, otherwise the
    whole body. The caller decides what to do with the result; this function has
    no opinion about where it lands.
    """
    cfg = ACTIONS.get(action)
    if not cfg:
        raise AuthoringError(f"'{action}' is not an editing action.")

    source = (text or "").strip()
    if action == "draft":
        # Drafting starts from the instruction, so an empty page is fine.
        if not (instruction or "").strip():
            raise AuthoringError("Describe the document you want and I will draft it.")
    elif len(source) < 2:
        raise AuthoringError("There is nothing to work on yet. Write something first, "
                             "or use 'Draft this for me'.")

    if len(source) > MAX_INPUT_CHARS:
        source = source[:MAX_INPUT_CHARS] + "\n\n[…document truncated for length…]"

    directive = cfg["prompt"]
    if action == "translate":
        directive = directive.format(target=(target or "Hindi").strip())
    elif action == "custom":
        directive = directive.format(instruction=(instruction or "").strip())

    parts = [directive, "", _FORMAT_RULE]
    if cfg.get("keep_structure"):
        parts += ["", _NO_NEW_STRUCTURE]
    elif title:
        # Only actions that may legitimately add structure get the title; give
        # it to a proofreader and it turns the title into a heading.
        parts += ["", f"The document is titled: {title}"]
    if context:
        parts += ["", f"Useful context: {context[:1500]}"]
    if action == "draft":
        parts += ["", "What the author asked for:", (instruction or "").strip()]
        if source:
            parts += ["", "Existing content to build on:", source]
    else:
        parts += ["", "--- DOCUMENT ---", source, "--- END DOCUMENT ---"]

    try:
        service = AIService(db_session=db)
    except ValueError as exc:
        raise AuthoringError(
            "AI editing is not configured. Add an API key under Settings → AI."
        ) from exc

    try:
        system = cfg["system"] + " " + _FORMAT_RULE
        if cfg.get("keep_structure"):
            system += " " + _NO_NEW_STRUCTURE

        response = service.chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "\n".join(parts)},
            ],
            max_tokens=3000,
            temperature=0.2 if action in ("grammar", "translate") else 0.4,
        )
        raw = (response.choices[0].message.content or "").strip()
    except Exception as exc:
        logger.exception(f"Authoring action '{action}' failed")
        raise AuthoringError(f"The model could not be reached: {exc}") from exc

    if not raw:
        raise AuthoringError("The model returned an empty response. Try again.")

    html = _to_html(raw)
    if not html:
        raise AuthoringError("The model returned nothing usable. Try again.")

    from .pdf_render import html_to_text

    return {
        "action": action,
        "label": cfg["label"],
        "replaces": cfg["replaces"],
        "html": html,
        "text": html_to_text(html),
    }


def _to_html(raw: str) -> str:
    """
    Normalise whatever came back into the small HTML subset.

    Models reach for markdown fences and stray headings however firmly you ask
    them not to, so strip those first and only then sanitise. Plain prose is
    wrapped into paragraphs, which is the common case for grammar fixes.
    """
    text = raw.strip()

    # Drop a fenced block wrapper if the whole reply is one.
    fence = re.match(r"^```[a-zA-Z]*\s*\n(.*?)\n?```$", text, re.S)
    if fence:
        text = fence.group(1).strip()

    # Some models still lead with "Here is the rewritten document:".
    text = re.sub(r"^(here (is|are)|sure[,!]?|certainly[,!]?)[^\n:]{0,80}:\s*\n+", "",
                  text, flags=re.I)

    looks_like_html = bool(re.search(r"<(p|h[1-6]|ul|ol|li|strong|em|br)\b", text, re.I))

    if not looks_like_html:
        text = _markdownish_to_html(text)

    cleaned = sanitize_html(text)
    # The renderer owns h1: an AI-supplied heading must not outrank the title.
    cleaned = re.sub(r"(?i)<(/?)h1>", r"<\1h2>", cleaned)
    return cleaned.strip()


def _markdownish_to_html(text: str) -> str:
    """Turn the light markdown models fall back to into the allowed subset."""
    out: list[str] = []
    bullets: list[str] = []

    def flush_bullets():
        if bullets:
            out.append("<ul>" + "".join(f"<li>{b}</li>" for b in bullets) + "</ul>")
            bullets.clear()

    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        if all(re.match(r"^\s*[-*•]\s+", ln) for ln in lines):
            for ln in lines:
                bullets.append(_inline(re.sub(r"^\s*[-*•]\s+", "", ln)))
            flush_bullets()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", block)
        if heading:
            flush_bullets()
            level = min(max(len(heading.group(1)), 2), 3)
            out.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            continue

        flush_bullets()
        out.append("<p>" + _inline(block).replace("\n", "<br>") + "</p>")

    flush_bullets()
    return "".join(out)


def _inline(text: str) -> str:
    text = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)
    return text
