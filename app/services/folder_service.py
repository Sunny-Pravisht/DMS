from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy import func

from ..models import DocumentFolder


def _get_user_folder(
    db: Session,
    user_id: str,
    folder_id: str,
) -> DocumentFolder | None:
    """Return a folder only when it belongs to the requested user."""
    return (
        db.query(DocumentFolder)
        .filter(
            DocumentFolder.id == folder_id,
            DocumentFolder.user_id == user_id,
        )
        .first()
    )


def create_folder(
    db: Session,
    user_id: str,
    name: str,
    *,
    parent_id: str | None = None,
    description: str | None = None,
) -> DocumentFolder:
    """
    Create a personal folder owned by user_id.

    If parent_id is supplied, the parent folder MUST belong to the same
    user. This prevents a user from creating a child folder underneath
    another user's folder.
    """
    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Folder name is required")

    if len(clean_name) > 255:
        raise ValueError("Folder name must be 255 characters or fewer")

    if parent_id:
        parent = _get_user_folder(db, user_id, parent_id)
        if not parent:
            raise ValueError("Parent folder was not found")

    existing = (
        db.query(DocumentFolder)
        .filter(
            DocumentFolder.user_id == user_id,
            DocumentFolder.parent_id == parent_id,
            func.lower(DocumentFolder.name) == clean_name.lower(),
        )
        .first()
    )
    if existing:
        return existing

    folder = DocumentFolder(
        user_id=user_id,
        parent_id=parent_id,
        name=clean_name,
        description=(description or "").strip()[:250] or None,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def list_user_folders(db: Session, user_id: str):
    """
    Return only folders owned by the signed-in user.

    The result intentionally contains no synthetic "My Folder" record.
    "My Folder" is a UI/workspace concept; actual records are user-created
    folders such as Work, Financial, Personal, etc.
    """
    folders = (
        db.query(DocumentFolder)
        .filter(
            DocumentFolder.user_id == user_id,
            func.lower(DocumentFolder.name) != "my folder",
        )
        .order_by(DocumentFolder.parent_id.asc(), DocumentFolder.name.asc())
        .all()
    )

    return [
        {
            "id": folder.id,
            "name": folder.name,
            "description": folder.description,
            "parent_id": folder.parent_id,
            "document_count": len(folder.documents),
            "child_count": len(folder.children),
            "created_at": folder.created_at,
            "updated_at": folder.updated_at,
        }
        for folder in folders
    ]


def get_user_folder(
    db: Session,
    user_id: str,
    folder_id: str,
) -> DocumentFolder | None:
    """Get a folder only if it belongs to the signed-in user."""
    return _get_user_folder(db, user_id, folder_id)


def rename_folder(
    db: Session,
    user_id: str,
    folder_id: str,
    name: str,
    description: str | None = None,
) -> DocumentFolder:
    """Rename a folder owned by the signed-in user."""
    folder = _get_user_folder(db, user_id, folder_id)
    if not folder:
        raise ValueError("Folder not found")

    clean_name = (name or "").strip()
    if not clean_name:
        raise ValueError("Folder name is required")
    if len(clean_name) > 255:
        raise ValueError("Folder name must be 255 characters or fewer")

    duplicate = (
        db.query(DocumentFolder)
        .filter(
            DocumentFolder.user_id == user_id,
            DocumentFolder.parent_id == folder.parent_id,
            func.lower(DocumentFolder.name) == clean_name.lower(),
            DocumentFolder.id != folder_id,
        )
        .first()
    )
    if duplicate:
        raise ValueError("A folder with this name already exists here")

    folder.name = clean_name

    if description is not None:
        folder.description = description.strip()[:250] or None

    db.commit()
    db.refresh(folder)
    return folder


def delete_folder(
    db: Session,
    user_id: str,
    folder_id: str,
) -> None:
    """
    Delete an empty folder owned by the signed-in user.

    We deliberately reject folders containing documents or subfolders so
    Requirement 4 cannot accidentally delete user content.
    """
    folder = _get_user_folder(db, user_id, folder_id)
    if not folder:
        raise ValueError("Folder not found")

    if folder.documents:
        raise ValueError(
            "Folder is not empty. Move or delete its documents before deleting it."
        )

    if folder.children:
        raise ValueError(
            "Folder contains subfolders. Delete or move the subfolders first."
        )

    db.delete(folder)
    db.commit()


def ensure_user_folder(
    db: Session,
    user_id: str,
    name: str,
    *,
    parent_id: str | None = None,
) -> DocumentFolder:
    """
    Backward-compatible helper.

    This helper no longer creates a global/synthetic 'My Folder'. It only
    works with an explicitly requested user-owned folder.
    """
    clean_name = (name or "").strip()

    existing = (
        db.query(DocumentFolder)
        .filter(
            DocumentFolder.user_id == user_id,
            DocumentFolder.parent_id == parent_id,
            func.lower(DocumentFolder.name) == clean_name.lower(),
        )
        .first()
    )
    if existing:
        return existing

    return create_folder(
        db,
        user_id,
        clean_name,
        parent_id=parent_id,
    )
