from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import DocumentFolder, User


def create_folder(db: Session, user_id: str, name: str, *, parent_id: str | None = None,
                 description: str | None = None) -> DocumentFolder:
    """Create a personal folder for a user and optionally nest it under another folder."""
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Folder name is required")

    existing = (
        db.query(DocumentFolder)
        .filter(DocumentFolder.user_id == user_id, DocumentFolder.name == clean_name,
                DocumentFolder.parent_id == parent_id)
        .first()
    )
    if existing:
        return existing

    folder = DocumentFolder(
        user_id=user_id,
        parent_id=parent_id,
        name=clean_name,
        description=(description or "")[:250] or None,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def list_user_folders(db: Session, user_id: str):
    """Return a lightweight folder list for the UI."""
    folders = (
        db.query(DocumentFolder)
        .filter(DocumentFolder.user_id == user_id)
        .order_by(DocumentFolder.name.asc())
        .all()
    )
    return [
        {
            "id": f.id,
            "name": f.name,
            "description": f.description,
            "parent_id": f.parent_id,
            "document_count": len(f.documents),
            "created_at": f.created_at,
        }
        for f in folders
    ]


def ensure_user_folder(db: Session, user_id: str, name: str) -> DocumentFolder:
    """Idempotent helper for the personal workspace."""
    folder = (
        db.query(DocumentFolder)
        .filter(DocumentFolder.user_id == user_id, DocumentFolder.name == name)
        .first()
    )
    if folder:
        return folder
    return create_folder(db, user_id, name)
