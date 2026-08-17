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

    # Same bytes, same version, already recorded: nothing new happened.
    existing = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document.id,
                DocumentVersion.version == label)
        .first()
    )
    if existing:
        return existing

    stored = source
    if copy_file:
        target_dir = source.parent / "versions"
        target_dir.mkdir(parents=True, exist_ok=True)
        stored = target_dir / f"{document.id}_v{label}{source.suffix}"
        if not stored.exists():
            try:
                shutil.copy2(source, stored)
            except OSError as exc:
                logger.warning(f"Could not copy version file: {exc}")
                stored = source

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
    """Newest first, which is the order people read a history in."""
    return (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.created_at.desc())
        .all()
    )


def compare_versions(db: Session, document_id: str, left_id: str, right_id: str) -> dict:
    """Compare two snapshots and return a diff summary for the UI."""
    left = get(db, document_id, left_id)
    right = get(db, document_id, right_id)
    if not left or not right:
        raise ValueError("Both versions must belong to the document.")

    left_path = Path(left.file_path)
    right_path = Path(right.file_path)

    def _read(path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    left_text = _read(left_path)
    right_text = _read(right_path)
    different = left_text != right_text
    return {
        "document_id": document_id,
        "left_version": left.version,
        "right_version": right.version,
        "different": different,
        "left_size": left.file_size,
        "right_size": right.file_size,
        "left_mime_type": left.mime_type,
        "right_mime_type": right.mime_type,
        "left_excerpt": left_text[:400],
        "right_excerpt": right_text[:400],
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
    db.commit()
    return capture(
        db,
        document,
        author=actor,
        note=f"Checked out v{snapshot.version}",
        version=snapshot.version,
    )


def get(db: Session, document_id: str, version_id: str) -> Optional[DocumentVersion]:
    return (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document_id,
                DocumentVersion.id == version_id)
        .first()
    )


def lock_current(db: Session, document: Document, note: str = "Approved and locked") -> None:
    """Called when an approval completes: freeze the version that was signed."""
    snapshot = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document.id,
                DocumentVersion.is_current.is_(True))
        .first()
    )
    if not snapshot:
        snapshot = capture(db, document, note=note, lock=True)
        return
    snapshot.is_locked = True
    snapshot.note = note[:200]
    db.commit()


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
