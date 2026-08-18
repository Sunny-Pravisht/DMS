"""
Document version history.

A version is a snapshot of the bytes, written whenever they change: on capture,
on every save from the Studio, and when an approval locks a version. The table
is append-only. "Restore v1.1" does not rewind history - it writes a *new*
version whose content happens to match v1.1, so the record of what happened
stays intact and the restore itself is visible in it.

Approved versions are locked. A locked version can be superseded by a newer one
but never overwritten, which is what makes "this is the version they signed" a
statement the system can actually stand behind.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from difflib import SequenceMatcher
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from loguru import logger
from sqlalchemy.orm import Session

from ..models import Document, DocumentVersion, User


def next_version(current: Optional[str], major: bool = False) -> str:
    try:
        parts = str(current or "1.0").split(".")
        hi, lo = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        hi, lo = 1, 0
    return f"{hi + 1}.0" if major else f"{hi}.{lo + 1}"


def capture(
    db: Session,
    document: Document,
    *,
    author: Optional[User] = None,
    note: str = "",
    version: Optional[str] = None,
    lock: bool = False,
    copy_file: bool = True,
) -> Optional[DocumentVersion]:
    """
    Record the document's current file as a version.

    The file is copied into a per-document `versions/` folder rather than
    referenced in place, because the live path is overwritten by the next save
    and a history pointing at overwritten bytes is worse than no history.
    """
    if not document.file_path:
        return None

    source = Path(document.file_path)
    if not source.exists():
        logger.warning(f"Version capture skipped, file missing: {source}")
        return None

    label = version or document.version or "1.0"

    stored = source
    if copy_file:
        target_dir = source.parent / "versions"
        target_dir.mkdir(parents=True, exist_ok=True)
        stored = target_dir / f"{document.id}_v{label}{source.suffix}"
        if not stored.exists() or lock:
            try:
                shutil.copy2(source, stored)
            except OSError as exc:
                logger.warning(f"Could not copy version file: {exc}")
                stored = source

    # If this version was already recorded, update its metadata/file if locking or updating
    existing = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document.id,
                DocumentVersion.version == label)
        .first()
    )
    if existing:
        if lock:
            existing.is_locked = True
        if note:
            existing.note = note[:200]
        if copy_file and stored.exists():
            existing.file_path = str(stored)
            existing.file_size = document.file_size
            existing.file_hash = document.file_hash
            existing.mime_type = document.mime_type
        db.commit()
        db.refresh(existing)
        return existing

    db.query(DocumentVersion).filter(
        DocumentVersion.document_id == document.id
    ).update({DocumentVersion.is_current: False})

    snapshot = DocumentVersion(
        document_id=document.id,
        version=label,
        file_path=str(stored),
        file_size=document.file_size,
        mime_type=document.mime_type,
        file_hash=document.file_hash,
        source_html=document.source_html,
        template_id=document.template_id,
        note=(note or "Saved")[:200],
        is_current=True,
        is_locked=lock,
        created_by=author.id if author else document.created_by,
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def history(db: Session, document_id: str) -> list[DocumentVersion]:
    """Newest first, which is the order people read a history in.
    Includes versions from ancestor documents if this document is a revision."""
    visited = set()
    all_versions: list[DocumentVersion] = []
    seen_ids = set()
    curr_id: Optional[str] = document_id
    while curr_id and curr_id not in visited:
        visited.add(curr_id)
        versions = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == curr_id)
            .order_by(DocumentVersion.created_at.desc())
            .all()
        )
        for v in versions:
            if v.id not in seen_ids:
                seen_ids.add(v.id)
                all_versions.append(v)
        doc = db.query(Document).filter(Document.id == curr_id).first()
        curr_id = doc.revision_of if doc else None

    all_versions.sort(key=lambda v: v.created_at if v.created_at else datetime.min, reverse=True)
    return all_versions


class _TextExtractor(HTMLParser):
    '''Turn composed HTML into readable comparison text.'''

    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"br", "p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag.lower() in {"p", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def _plain_text(value: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(value or "")
    text = "".join(extractor.parts)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _version_text(version: DocumentVersion, file_bytes: bytes) -> str:
    if version.source_html:
        return _plain_text(version.source_html)
    if (version.mime_type or "").endswith("pdf"):
        try:
            from PyPDF2 import PdfReader
            import io
            return "\n".join((page.extract_text() or "") for page in PdfReader(io.BytesIO(file_bytes)).pages)
        except Exception:
            return ""
    return _plain_text(file_bytes.decode("utf-8", errors="replace"))


def _comparison_excerpt(left_text: str, right_text: str, limit: int = 1200) -> tuple[str, str]:
    '''Return only lines that differ between the two text versions.'''
    left_lines = left_text.splitlines()
    right_lines = right_text.splitlines()
    matcher = SequenceMatcher(None, left_lines, right_lines)
    left_changed = []
    right_changed = []

    for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        if tag == "equal":
            continue
        if tag in {"replace", "delete"}:
            left_changed.extend(left_lines[left_start:left_end])
        if tag in {"replace", "insert"}:
            right_changed.extend(right_lines[right_start:right_end])

    left_excerpt = "\n".join(left_changed) or "No changed lines"
    right_excerpt = "\n".join(right_changed) or "No changed lines"
    return left_excerpt[:limit], right_excerpt[:limit]


def compare_versions(db: Session, document_id: str, left_id: str, right_id: str) -> dict:
    """Compare two snapshots and return an honest summary for the UI."""
    left = get(db, document_id, left_id)
    right = get(db, document_id, right_id)
    if not left or not right:
        raise ValueError("Both versions must belong to the document.")

    left_path = Path(left.file_path)
    right_path = Path(right.file_path)

    left_bytes = left_path.read_bytes() if left_path.exists() else b""
    right_bytes = right_path.read_bytes() if right_path.exists() else b""
    different = left_bytes != right_bytes

    # Text can be previewed meaningfully. For binary formats (PDFs and images)
    # the byte/hash result is still accurate, but decoding them would invent
    # gibberish and make two different files look identical.
    # PDFs are binary documents even when PyPDF2 can extract text from them.
    # Their layout, images, stamps, and signatures must be compared visually,
    # so the viewer can show the two exact PDF files side by side.
    def _is_text_version(version: DocumentVersion) -> bool:
        mime = (version.mime_type or "").lower()
        # source_html can remain populated from an earlier Studio edit even
        # after the document is exported to PDF. MIME type wins here: a PDF
        # must always use the visual side-by-side comparison.
        if mime == "application/pdf" or mime.startswith("image/"):
            return False
        return mime.startswith("text/") or bool(version.source_html)

    text_like = all(_is_text_version(v) for v in (left, right))
    extracted_text = False
    text_changed = False
    if text_like:
        left_text = _version_text(left, left_bytes)
        right_text = _version_text(right, right_bytes)
        extracted_text = bool(left_text.strip() or right_text.strip())
        # A PDF may be byte-different but contain no extractable text (for
        # example, a scanned page or a layout-only edit). Do not render that
        # case as a successful text comparison with two misleading empty panes.
        if not extracted_text:
            text_like = False
            left_text = right_text = ""
        else:
            original_left, original_right = left_text, right_text
            text_changed = original_left != original_right
            left_text, right_text = _comparison_excerpt(original_left, original_right)
    else:
        left_text = right_text = ""

    return {
        "document_id": document_id,
        "left_version": left.version,
        "right_version": right.version,
        "different": different,
        "left_size": left.file_size,
        "right_size": right.file_size,
        "left_mime_type": left.mime_type,
        "right_mime_type": right.mime_type,
        "left_hash": left.file_hash,
        "right_hash": right.file_hash,
        "comparison_mode": "text" if text_like else "binary",
        "text_changed": text_changed,
        "left_excerpt": left_text[:400],
        "right_excerpt": right_text[:400],
        "comparison_note": (
            "The files differ, but neither version contains extractable text. Open both versions above to inspect the actual pages."
            if different and not extracted_text else
            "The PDF files are different, but their extracted text is identical. The change is visual, layout-related, an image/signature/stamp, or PDF metadata. Open both versions above to inspect the actual pages."
            if different and extracted_text and not text_changed else None
        ),
    }


def checkout_version(db: Session, document: Document, version_id: str,
                    *, actor: Optional[User] = None) -> DocumentVersion:
    """Check out a historical version as the current working copy."""
    snapshot = get(db, document.id, version_id)
    if not snapshot:
        raise FileNotFoundError("Version not found")

    source = Path(snapshot.file_path)
    if not source.exists():
        raise FileNotFoundError("That version's file is no longer in storage.")

    target = Path(document.file_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)

    document.file_size = source.stat().st_size
    document.mime_type = snapshot.mime_type or document.mime_type
    document.source_html = snapshot.source_html or document.source_html
    document.template_id = snapshot.template_id or document.template_id
    document.version = snapshot.version
    document.updated_at = datetime.utcnow()
    try:
        from ..utils.file_security import calculate_file_hash
        document.file_hash = calculate_file_hash(target)
    except Exception:
        logger.warning("Could not refresh the file hash while checking out a version")

    # Checkout selects an existing immutable snapshot; it must not create a
    # second record with the same version label. Mark exactly that snapshot as
    # the active working version so history and the live file agree.
    db.query(DocumentVersion).filter(
        DocumentVersion.document_id == document.id
    ).update({DocumentVersion.is_current: False})
    snapshot.is_current = True
    db.commit()
    db.refresh(snapshot)
    return snapshot


def get(db: Session, document_id: str, version_id: str) -> Optional[DocumentVersion]:
    snapshot = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.id == version_id)
        .first()
    )
    if not snapshot:
        return None
    if snapshot.document_id == document_id:
        return snapshot
    # Check if the snapshot belongs to an ancestor in the revision chain
    visited = set()
    curr_id: Optional[str] = document_id
    while curr_id and curr_id not in visited:
        visited.add(curr_id)
        if snapshot.document_id == curr_id:
            return snapshot
        doc = db.query(Document).filter(Document.id == curr_id).first()
        curr_id = doc.revision_of if doc else None
    return None


def lock_current(
    db: Session,
    document: Document,
    note: str = "Approved and locked",
    update_file: bool = True,
) -> Optional[DocumentVersion]:
    """Called when an approval or publish completes: freeze the current version."""
    snapshot = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document.id,
                DocumentVersion.is_current.is_(True))
        .first()
    )
    if not snapshot:
        return capture(db, document, note=note, lock=True)

    if update_file and document.file_path:
        source = Path(document.file_path)
        if source.exists():
            target_dir = source.parent / "versions"
            target_dir.mkdir(parents=True, exist_ok=True)
            label = document.version or snapshot.version or "1.0"
            stored = target_dir / f"{document.id}_v{label}{source.suffix}"
            try:
                shutil.copy2(source, stored)
                snapshot.file_path = str(stored)
            except OSError as exc:
                logger.warning(f"Could not update version file on lock: {exc}")
                snapshot.file_path = str(source)
            snapshot.file_size = document.file_size
            snapshot.file_hash = document.file_hash
            snapshot.mime_type = document.mime_type

    snapshot.is_locked = True
    snapshot.note = note[:200]
    db.commit()
    db.refresh(snapshot)
    return snapshot


def restore(db: Session, document: Document, snapshot: DocumentVersion,
            actor: Optional[User] = None) -> DocumentVersion:
    """
    Bring an older version back as the newest one.

    Forward-only: the old version stays exactly where it is in the history and
    a new version is written on top carrying its content.
    """
    source = Path(snapshot.file_path)
    if not source.exists():
        raise FileNotFoundError("That version's file is no longer in storage.")

    live = Path(document.file_path)
    live.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, live)

    document.file_size = source.stat().st_size
    document.source_html = snapshot.source_html
    document.template_id = snapshot.template_id
    document.version = next_version(document.version)
    document.updated_at = datetime.utcnow()

    from ..utils.file_security import calculate_file_hash
    try:
        document.file_hash = calculate_file_hash(live)
    except Exception:
        pass

    db.commit()

    return capture(
        db, document, author=actor,
        note=f"Restored from v{snapshot.version}",
        version=document.version,
    )
