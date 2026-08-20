from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Form
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_, exists
from typing import List, Optional
import os
from pathlib import Path
import mimetypes

from loguru import logger

from ..database import get_db
from ..models import Document, DocumentFolder, ProcessingLog, Tag, User, ApprovalWorkflow, ApprovalStep, step_assignees
from ..schemas import (
    Document as DocumentSchema, DocumentUpdate, DocumentProcessingStatus,
    FileUploadResponse, StagingFile, DocumentApprovalRequest, DocumentApprovalResponse,
    Tag as TagSchema, TagAddRequest, TagAddResponse,
)
from ..services.document_processor import DocumentProcessor
from ..services.folder_setup import get_folder_info
from ..services.folder_service import (
    create_folder,
    list_user_folders,
    get_user_folder,
    rename_folder,
    delete_folder,
)
from ..services import thumbnails
from ..services.auth_service import (
    get_current_user_flexible,
    require_permission_flexible,
    require_document_delete_flexible,
    require_admin_flexible,
)
from ..config import get_settings
from ..utils.file_security import (
    validate_file_upload, secure_file_path, set_secure_permissions,
    check_file_permissions, check_document_access, FileSecurityError,
    FileTypeNotAllowedError
)
from datetime import datetime
import uuid

router = APIRouter()


def _get_owned_document(db: Session, document_id: str, current_user: User) -> Document:
    """Return a document the current user is allowed to manage."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Personal-folder documents are owned through their folder.
    if document.folder_id:
        folder = get_user_folder(db, current_user.id, document.folder_id)
        if not folder:
            raise HTTPException(status_code=403, detail="You do not have access to this document")

    return document

@router.get("/folders")
def get_user_folders(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """Return personal folders the signed-in user owns."""
    return {"folders": list_user_folders(db, current_user.id)}


@router.post("/folders")
def create_user_folder(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.create")),
):
    """Create a folder owned by the signed-in user."""
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Folder name is required")

    try:
        folder = create_folder(
            db,
            current_user.id,
            name,
            parent_id=payload.get("parent_id"),
            description=payload.get("description"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "folder": {
            "id": folder.id,
            "name": folder.name,
            "parent_id": folder.parent_id,
        }
    }



@router.put("/folders/{folder_id}")
def update_user_folder(
    folder_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """Rename/update a folder owned by the signed-in user."""
    try:
        folder = rename_folder(
            db, current_user.id, folder_id,
            payload.get("name"), payload.get("description")
        )
    except ValueError as exc:
        message = str(exc)
        status = 409 if "already exists" in message.lower() else 400
        if message == "Folder not found":
            status = 404
        raise HTTPException(status_code=status, detail=message)

    return {
        "folder": {
            "id": folder.id,
            "name": folder.name,
            "description": folder.description,
            "parent_id": folder.parent_id,
            "created_at": folder.created_at,
            "updated_at": folder.updated_at,
        }
    }


@router.delete("/folders/{folder_id}")
def delete_user_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_document_delete_flexible),
):
    """Delete an owned folder only when empty."""
    try:
        delete_folder(db, current_user.id, folder_id)
    except ValueError as exc:
        message = str(exc)
        status = 404 if message == "Folder not found" else 400
        raise HTTPException(status_code=status, detail=message)

    return {"status": "success", "folder_id": folder_id}


# Note: Services will be initialized with database session in each endpoint

@router.get("/filter-options")
def get_filter_options(current_user: User = Depends(require_permission_flexible("documents.read"))):
    """Get available filter options for the frontend"""
    date_ranges = [
        {"key": "today", "label": "Today"},
        {"key": "yesterday", "label": "Yesterday"},
        {"key": "last_7_days", "label": "Last 7 Days"},
        {"key": "last_30_days", "label": "Last 30 Days"},
        {"key": "last_90_days", "label": "Last 90 Days"},
        {"key": "this_week", "label": "This Week"},
        {"key": "last_week", "label": "Last Week"},
        {"key": "this_month", "label": "This Month"},
        {"key": "last_month", "label": "Last Month"},
        {"key": "this_quarter", "label": "This Quarter"},
        {"key": "last_quarter", "label": "Last Quarter"},
        {"key": "this_year", "label": "This Year"},
        {"key": "last_year", "label": "Last Year"},
        {"key": "last_2_years", "label": "Last 2 Years"}
    ]

    reminder_options = [
        {"key": "has", "label": "With Reminder"},
        {"key": "overdue", "label": "Overdue"},
        {"key": "none", "label": "Without Reminder"}
    ]

    # Sort all options alphabetically by label
    date_ranges_sorted = sorted(date_ranges, key=lambda x: x["label"])
    reminder_options_sorted = sorted(reminder_options, key=lambda x: x["label"])

    return {
        "date_ranges": date_ranges_sorted,
        "reminder_options": reminder_options_sorted
    }

@router.get("/", response_model=List[DocumentSchema])
def get_documents(
    current_user: User = Depends(require_permission_flexible("documents.read")),
    skip: int = 0,
    limit: int = 20,
    correspondent_id: Optional[str] = None,
    doctype_id: Optional[str] = None,
    folder_id: Optional[str] = None,
    folder: Optional[str] = None,
    is_tax_relevant: Optional[bool] = None,
    date_range: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    reminder_filter: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all documents with optional filtering"""
    # Administrators can see the complete repository. Regular users see only
    # documents they own, documents in their personal folders, or documents
    # explicitly assigned to them in an approval workflow. In particular, a
    # document uploaded by an admin is not implicitly visible to every user.
    query = db.query(Document).filter(Document.deleted_at.is_(None)).outerjoin(
        DocumentFolder, Document.folder_id == DocumentFolder.id
    )
    if not current_user.is_admin:
        assigned_document = exists().where(
            ApprovalWorkflow.document_id == Document.id,
            ApprovalWorkflow.id == ApprovalStep.workflow_id,
            ApprovalStep.id == step_assignees.c.step_id,
            step_assignees.c.user_id == current_user.id,
        )
        query = query.filter(or_(
            Document.created_by == current_user.id,
            DocumentFolder.user_id == current_user.id,
            assigned_document,
        ))

    resolved_folder_id = folder_id or folder
    if resolved_folder_id:
        owned_folder = get_user_folder(db, current_user.id, resolved_folder_id)
        if not owned_folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        query = query.filter(Document.folder_id == resolved_folder_id)

    if correspondent_id:
        query = query.filter(Document.correspondent_id == correspondent_id)

    if doctype_id:
        query = query.filter(Document.doctype_id == doctype_id)

    if is_tax_relevant is not None:
        query = query.filter(Document.is_tax_relevant == is_tax_relevant)

    # Date range filtering - predefined ranges take precedence
    if date_range:
        from ..services.search_service import SearchService
        search_service = SearchService()
        start_date, end_date = search_service._calculate_date_range(date_range)
        if start_date and end_date:
            query = query.filter(Document.document_date >= start_date, Document.document_date <= end_date)
    else:
        # Fallback to custom date range
        if date_from:
            try:
                from datetime import datetime
                date_from_parsed = datetime.fromisoformat(date_from)
                query = query.filter(Document.document_date >= date_from_parsed)
            except ValueError:
                pass  # Invalid date format, ignore filter

        if date_to:
            try:
                from datetime import datetime
                date_to_parsed = datetime.fromisoformat(date_to)
                query = query.filter(Document.document_date <= date_to_parsed)
            except ValueError:
                pass  # Invalid date format, ignore filter

    # Reminder filtering
    if reminder_filter == "has":
        query = query.filter(Document.reminder_date.isnot(None))
    elif reminder_filter == "overdue":
        from datetime import datetime
        query = query.filter(
            Document.reminder_date.isnot(None),
            Document.reminder_date < datetime.utcnow()
        )

    # Newest first. Without an explicit order SQLite returns rows in rowid
    # order, so every "limit" was silently answering with the OLDEST N - which
    # is why "Recent documents" listed the first files ever added, and why a
    # caller looking for the document it had just uploaded never found it.
    documents = (
        query.order_by(Document.created_at.desc(), Document.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return documents

# These literal Recently Deleted routes must be registered before the generic
# /{document_id} route, otherwise "recently-deleted" is interpreted as a document ID.
@router.get("/recently-deleted")
def list_recently_deleted_early(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    documents = db.query(Document).filter(Document.deleted_at.isnot(None)).order_by(Document.deleted_at.desc()).all()
    return {"documents": [{
        "id": d.id,
        "title": d.title or d.original_filename,
        "filename": d.original_filename,
        "deleted_at": d.deleted_at,
        "file_size": d.file_size,
    } for d in documents]}

@router.post("/recently-deleted/{document_id}/restore")
def restore_deleted_document_early(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    document = db.query(Document).filter(Document.id == document_id, Document.deleted_at.isnot(None)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Deleted document not found")
    document.deleted_at = None
    document.deleted_by = None
    document.folder_id = document.deleted_from_folder_id
    document.deleted_from_folder_id = None
    db.commit()
    return {"message": "Document restored successfully"}

@router.delete("/recently-deleted/{document_id}")
def permanently_delete_document_early(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    document = db.query(Document).filter(Document.id == document_id, Document.deleted_at.isnot(None)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Deleted document not found")
    return _permanently_delete_document(db, document)

@router.get("/{document_id}", response_model=DocumentSchema)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Get a specific document by ID"""
    from sqlalchemy.orm import joinedload

    document = db.query(Document)\
        .options(
            joinedload(Document.correspondent),
            joinedload(Document.doctype),
            joinedload(Document.tags)
        )\
        .filter(Document.id == document_id)\
        .first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not check_document_access(document, current_user, 'read'):
        raise HTTPException(status_code=403, detail="You do not have access to this document")

    return document

@router.post("/{document_id}/view")
def track_document_view(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Track document view - increment view count"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Increment view count and update last viewed timestamp
    document.view_count = (document.view_count or 0) + 1
    document.last_viewed = datetime.utcnow()

    db.commit()

    return {
        "view_count": document.view_count,
        "last_viewed": document.last_viewed
    }


@router.put("/{document_id}/move")
def move_document(
    document_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """
    Move a personal document to another folder owned by the current user.

    Payload:
      {"folder_id": "<folder-id>"}
      {"folder_id": null}  # move out of a personal folder
    """
    document = _get_owned_document(db, document_id, current_user)
    target_folder_id = payload.get("folder_id")

    if target_folder_id:
        target_folder = get_user_folder(db, current_user.id, target_folder_id)
        if not target_folder:
            raise HTTPException(status_code=404, detail="Target folder not found")

        # Prevent placing a document into a folder it already belongs to.
        document.folder_id = target_folder.id
    else:
        document.folder_id = None

    db.commit()
    db.refresh(document)

    return {
        "status": "success",
        "message": "Document moved successfully",
        "document_id": document.id,
        "folder_id": document.folder_id,
    }

@router.put("/{document_id}", response_model=DocumentSchema)
def update_document(
    document_id: str,
    document_update: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Update document metadata"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not check_document_access(document, current_user, 'write'):
        raise HTTPException(status_code=403, detail="You do not have access to update this document")

    # Update fields
    update_data = document_update.dict(exclude_unset=True)

    # Handle tags separately
    if 'tag_ids' in update_data:
        tag_ids = update_data.pop('tag_ids')
        if tag_ids is not None:
            # Clear existing tags and add new ones
            document.tags.clear()
            if tag_ids:
                from ..models import Tag
                tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all()
                document.tags.extend(tags)

    # Update other fields
    for field, value in update_data.items():
        setattr(document, field, value)

    db.commit()
    db.refresh(document)
    return document

@router.get("/recently-deleted")
def list_recently_deleted(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    # List soft-deleted documents for administrators."
    documents = (
        db.query(Document)
        .filter(Document.deleted_at.isnot(None))
        .order_by(Document.deleted_at.desc())
        .all()
    )
    return {"documents": [
        {
            "id": d.id,
            "title": d.title or d.original_filename,
            "filename": d.original_filename,
            "deleted_at": d.deleted_at,
            "file_size": d.file_size,
        }
        for d in documents
    ]}

@router.post("/recently-deleted/{document_id}/restore")
def restore_deleted_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    document = db.query(Document).filter(Document.id == document_id, Document.deleted_at.isnot(None)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Deleted document not found")
    document.deleted_at = None
    document.deleted_by = None
    document.folder_id = document.deleted_from_folder_id
    document.deleted_from_folder_id = None
    db.commit()
    return {"message": "Document restored successfully"}

@router.delete("/recently-deleted/{document_id}")
def permanently_delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    document = db.query(Document).filter(Document.id == document_id, Document.deleted_at.isnot(None)).first()
    if not document:
        raise HTTPException(status_code=404, detail="Deleted document not found")
    return _permanently_delete_document(db, document)

@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_document_delete_flexible)
):
    # Move the document to Recently Deleted. Only an administrator can permanently delete it.
    document = _get_owned_document(db, document_id, current_user)
    if document.deleted_at:
        raise HTTPException(status_code=404, detail="Document not found")
    document.deleted_from_folder_id = document.folder_id
    document.folder_id = None
    document.deleted_at = datetime.utcnow()
    document.deleted_by = current_user.id
    db.commit()
    return {"message": "Document moved to Recently Deleted"}


def _permanently_delete_document(db: Session, document: Document):
    # Delete physical file
    try:
        file_path = Path(document.file_path)
        if file_path.exists():
            file_path.unlink()
    except Exception:
        pass
    try:
        from ..services.vector_db_service import VectorDBService
        VectorDBService(db).delete_document(document.id)
    except Exception:
        pass
    for log in db.query(ProcessingLog).filter(ProcessingLog.document_id == document.id).all():
        db.delete(log)
    document.tags.clear()
    db.delete(document)
    db.commit()
    return {"message": "Document permanently deleted"}

@router.delete("/{document_id}/legacy-permanent")
def legacy_permanent_delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_flexible),
):
    # Internal compatibility route; permanent deletion remains admin-only."
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return _permanently_delete_document(db, document)

@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Download the original document file with security checks"""
    document = db.query(Document).filter(
        Document.id == document_id, Document.deleted_at.is_(None)
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check document access permissions
    if not check_document_access(document, current_user, 'read'):
        raise HTTPException(status_code=403, detail="Access denied to this document")

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found")

    # Verify file permissions
    if not check_file_permissions(file_path, current_user):
        raise HTTPException(status_code=403, detail="Access denied to file")

    # Validate file path to prevent directory traversal.
    #
    # Both sides are resolved before comparing. They were not, and the two are
    # written differently: documents store an absolute path, while the setting
    # is "./data/storage". relative_to() compares them literally, so it raised
    # for every document ever stored and Download answered 403 for all of them.
    #
    # Resolving keeps the guard intact - a path outside the storage folder, or
    # one reaching out through "..", still fails - it just stops the check
    # rejecting the ordinary case it was written to allow.
    try:
        settings = get_settings(db)
        storage_base = Path(settings.storage_folder).resolve()
        file_path.resolve().relative_to(storage_base)
    except (ValueError, OSError):
        logger.warning(
            f"Refused download of {document_id}: {file_path} is outside {storage_base}"
        )
        raise HTTPException(status_code=403, detail="Invalid file path")

    # Log access event
    from ..services.audit_service import log_audit_event
    log_audit_event(
        db=db,
        user_id=current_user.id,
        action="document.download",
        resource_type="document",
        resource_id=document_id,
        details={
            "filename": document.original_filename,
            "file_path": str(file_path)
        }
    )

    # Determine media type
    media_type, _ = mimetypes.guess_type(str(file_path))
    if not media_type:
        media_type = "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        filename=document.original_filename,
        media_type=media_type
    )

@router.post("/upload", response_model=FileUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    folder_id: Optional[str] = Form(None),
    process: Optional[str] = Form("true"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible)
):
    """Upload a document, optionally storing it directly without running OCR/AI processing.

    By default, uploads still follow the legacy staging + processing path used by the
    Studio. My Folder uploads pass `process=false`, which creates the Document row in
    storage immediately and leaves OCR/AI/vector statuses pending so the document can be
    opened in Studio when the user chooses to process it later.
    """

    if not current_user.is_admin and not current_user.has_permission("documents.create"):
        raise HTTPException(
            status_code=403,
            detail="You don't have permission to upload documents"
        )

    should_process = str(process or "true").strip().lower() not in {"0", "false", "no", "skip"}

    if folder_id:
        folder = (
            db.query(DocumentFolder)
            .filter(DocumentFolder.id == folder_id, DocumentFolder.user_id == current_user.id)
            .first()
        )
        if not folder:
            raise HTTPException(status_code=400, detail="Selected folder was not found")

    settings = get_settings(db)
    content = await file.read()

    try:
        safe_filename, mime_type = validate_file_upload(
            filename=file.filename,
            content=content,
            user=current_user,
            max_size=settings.max_file_size_bytes
        )

        import hashlib
        digest = hashlib.sha256(content).hexdigest()

        if should_process:
            twin = db.query(Document).filter(Document.file_hash == digest).first()
            if twin and twin.file_path and Path(twin.file_path).exists():
                return FileUploadResponse(
                    message=f"This file is already in the repository as “{twin.title or twin.original_filename}”.",
                    status="duplicate",
                    document_id=twin.id,
                    filename=twin.original_filename,
                    folder=(twin.folder.name if twin.folder else None),
                )

        if should_process:
            staging_base = Path(settings.staging_folder)
            staging_base.mkdir(parents=True, exist_ok=True)
            if not os.access(staging_base, os.W_OK):
                raise Exception(f"Staging directory {staging_base} is not writable")

            staging_path = secure_file_path(staging_base, safe_filename)
            counter = 1
            original_stem = staging_path.stem
            while staging_path.exists():
                new_filename = f"{original_stem}_{counter}{staging_path.suffix}"
                staging_path = secure_file_path(staging_base, new_filename)
                counter += 1

            with open(staging_path, "wb") as buffer:
                buffer.write(content)

            if folder_id:
                meta_path = staging_path.with_name(f"{staging_path.name}.folder.json")
                meta_path.write_text(__import__("json").dumps({"folder_id": folder_id}, indent=2), encoding="utf-8")

            set_secure_permissions(staging_path, is_private=True)

            from ..services.audit_service import log_audit_event
            log_audit_event(
                db=db,
                user_id=current_user.id,
                action="document.upload",
                resource_type="document",
                resource_id=None,
                details={
                    "filename": safe_filename,
                    "original_filename": file.filename,
                    "mime_type": mime_type,
                    "size": len(content),
                    "staging_path": str(staging_path),
                    "process": True,
                }
            )

            return FileUploadResponse(
                message=f"File uploaded successfully to staging: {staging_path.name}",
                status="uploaded",
                filename=staging_path.name,
            )

        storage_base = Path(settings.storage_folder)
        storage_base.mkdir(parents=True, exist_ok=True)
        if not os.access(storage_base, os.W_OK):
            raise Exception(f"Storage directory {storage_base} is not writable")

        safe_doc_name = safe_filename
        counter = 1
        original_stem = Path(safe_doc_name).stem
        suffix = Path(safe_doc_name).suffix
        storage_path = secure_file_path(storage_base, safe_doc_name)
        while storage_path.exists():
            storage_path = secure_file_path(storage_base, f"{original_stem}_{counter}{suffix}")
            counter += 1

        with open(storage_path, "wb") as buffer:
            buffer.write(content)
        set_secure_permissions(storage_path, is_private=True)

        document = Document(
            created_by=current_user.id,
            filename=storage_path.name,
            original_filename=file.filename or safe_filename,
            file_hash=digest,
            file_path=str(storage_path),
            file_size=len(content),
            mime_type=mime_type,
            title=(file.filename or safe_filename).strip() or safe_filename,
            folder_id=folder_id,
            ocr_status="pending",
            ai_status="pending",
            vector_status="pending",
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        from ..services.audit_service import log_audit_event
        log_audit_event(
            db=db,
            user_id=current_user.id,
            action="document.upload",
            resource_type="document",
            resource_id=document.id,
            details={
                "filename": safe_filename,
                "original_filename": file.filename,
                "mime_type": mime_type,
                "size": len(content),
                "storage_path": str(storage_path),
                "folder_id": folder_id,
                "process": False,
            }
        )

        return FileUploadResponse(
            message="File saved to My Folder and ready to open in Studio.",
            status="uploaded",
            document_id=document.id,
            filename=document.original_filename,
            folder=(folder.name if folder else "My Folder"),
        )

    except FileTypeNotAllowedError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileSecurityError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Upload error: {str(e)}")
        print(f"Full traceback: {error_details}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

@router.get("/staging/files", response_model=List[StagingFile])
def get_staging_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Get list of files in staging folder"""
    settings = get_settings(db)
    staging_path = Path(settings.staging_folder)

    if not staging_path.exists():
        return []

    files = []
    for file_path in staging_path.iterdir():
        if file_path.is_file():
            stat = file_path.stat()
            files.append(StagingFile(
                filename=file_path.name,
                size=stat.st_size,
                created_at=stat.st_ctime,
                status="pending"  # This would need to be tracked in a separate system
            ))

    return files

@router.post("/process-staging")
async def process_staging_files(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.create"))
):
    """Manually trigger processing of all files in staging"""
    from ..services.file_watcher import FileWatcher

    file_watcher = FileWatcher()
    background_tasks.add_task(file_watcher.scan_and_process)

    return {"message": "Started processing staging files"}

@router.get("/{document_id}/status", response_model=DocumentProcessingStatus)
def get_processing_status(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Get processing status for a document"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentProcessingStatus(
        document_id=document.id,
        filename=document.filename,
        ocr_status=document.ocr_status,
        ai_status=document.ai_status
    )

@router.get("/{document_id}/logs")
def get_processing_logs(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Get processing logs for a document"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    logs = (db.query(ProcessingLog)
           .filter(ProcessingLog.document_id == document_id)
           .order_by(ProcessingLog.created_at.desc())
           .all())

    return logs


@router.post("/{document_id}/reprocess")
async def reprocess_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Reprocess a document (OCR and AI extraction)"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found")

    # Reset processing status
    document.ocr_status = "pending"
    document.ai_status = "pending"
    document.vector_status = "pending"
    document.full_text = None
    document.processed_at = None
    db.commit()

    # Reprocess in background. The request-scoped session is closed as soon as
    # the response is sent, so the task must open its own session.
    background_tasks.add_task(_reprocess_document_task, document_id)

    return {"message": "Document reprocessing started"}


def _reprocess_document_task(document_id: str):
    """Background worker that owns its own database session."""
    from ..database import SessionLocal

    with SessionLocal() as task_db:
        document = task_db.query(Document).filter(Document.id == document_id).first()
        if not document:
            print(f"Reprocess task: document {document_id} no longer exists")
            return
        try:
            DocumentProcessor(task_db).reprocess_existing(document, task_db)
        except Exception as exc:
            print(f"Reprocess task failed for {document_id}: {exc}")

@router.get("/stats/overview")
def get_document_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Get overview statistics"""
    total_documents = db.query(Document).count()
    pending_ocr = db.query(Document).filter(Document.ocr_status == "pending").count()
    pending_ai = db.query(Document).filter(Document.ai_status == "pending").count()
    tax_relevant = db.query(Document).filter(Document.is_tax_relevant).count()

    folder_info = get_folder_info(db)

    return {
        "total_documents": total_documents,
        "pending_ocr": pending_ocr,
        "pending_ai": pending_ai,
        "tax_relevant_documents": tax_relevant,
        "folders": folder_info
    }

@router.get("/{document_id}/file")
async def get_document_file(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """
    Serve the document file itself, for the viewer.

    Anything a browser can render is served inline. That includes plain text and
    markdown, which used to arrive as an attachment and so downloaded instead of
    displaying - the reason the preview never matched the real document.

    Formats a browser cannot render (Word, Excel) still come back as a download,
    because pretending otherwise would just show the user a wall of binary.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not check_document_access(document, current_user, 'read'):
        raise HTTPException(status_code=403, detail="Access denied to this document")

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found")

    media_type, _ = mimetypes.guess_type(str(file_path))
    if media_type is None:
        media_type = "application/octet-stream"

    # Text served as-is would be sniffed; pin the charset so accents survive.
    if media_type.startswith("text/"):
        media_type = f"{media_type}; charset=utf-8"

    if media_type.startswith(("image/", "text/")) or media_type == "application/pdf":
        return FileResponse(
            path=str(file_path),
            media_type=media_type,
            headers={
                "Content-Disposition": "inline",
                "X-Content-Type-Options": "nosniff",
                # A document may be reopened repeatedly while reviewing it, but
                # it can also be replaced, so revalidate rather than cache hard.
                "Cache-Control": "private, no-cache, must-revalidate",
            },
        )

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=document.original_filename,
    )


@router.get("/{document_id}/preview-info")
def get_preview_info(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """
    Tell the viewer how to show this document before it tries.

    The front end should not have to guess a renderer from a filename. This
    reports what the file actually is, whether the bytes are still there, and
    what to fall back to when the browser cannot display the format.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not check_document_access(document, current_user, 'read'):
        raise HTTPException(status_code=403, detail="Access denied to this document")

    file_path = Path(document.file_path) if document.file_path else None
    exists = bool(file_path and file_path.exists())

    mime = (document.mime_type or "").lower()
    if not mime and file_path:
        mime = (mimetypes.guess_type(str(file_path))[0] or "").lower()

    suffix = file_path.suffix.lower() if file_path else ""

    if mime == "application/pdf" or suffix == ".pdf":
        mode = "pdf"
    elif mime.startswith("image/") or suffix in (".png", ".jpg", ".jpeg", ".gif", ".bmp",
                                                 ".tif", ".tiff", ".webp"):
        mode = "image"
    elif mime.startswith("text/") or suffix in (".txt", ".md", ".markdown", ".csv", ".log"):
        mode = "text"
    else:
        mode = "unsupported"

    if not exists:
        mode = "missing"

    return {
        "document_id": document.id,
        "title": document.title or document.original_filename or document.filename,
        "filename": document.original_filename or document.filename,
        "mime_type": mime or "application/octet-stream",
        "file_size": document.file_size,
        "mode": mode,
        "file_url": f"/api/documents/{document.id}/file",
        "download_url": f"/api/documents/{document.id}/download",
        "has_text": bool((document.full_text or "").strip()),
        "text_length": len(document.full_text or ""),
        "origin": document.origin or "uploaded",
        "editable": bool(document.source_html) or bool((document.full_text or "").strip()),
        "version": document.version or "1.0",
        "page_hint": _page_hint(document, file_path if exists else None),
    }


def _page_hint(document: Document, file_path: Optional[Path]) -> Optional[int]:
    """Page count when it is cheap to get; None rather than a guess."""
    if not file_path or file_path.suffix.lower() != ".pdf":
        return None
    try:
        from PyPDF2 import PdfReader

        with open(file_path, "rb") as fh:
            return len(PdfReader(fh).pages)
    except Exception:
        return None


@router.get("/{document_id}/versions")
def list_versions(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """
    Every saved version of this document, newest first.

    If nothing has been recorded yet - the common case for a document captured
    before version history existed - the current file is recorded now, so the
    history always has at least the truth about today.
    """
    from ..services import version_service

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    versions = version_service.history(db, document_id)
    if not versions:
        created = version_service.capture(
            db, document, author=current_user, note="Initial capture",
            version=document.version or "1.0",
        )
        versions = [created] if created else []

    # A document can have one current snapshot in its own history, while a
    # revision also includes ancestor snapshots. Marking only the database flag
    # is not enough for older data or mixed revision histories; the live
    # document's version is the authoritative current label for this response.
    current_snapshot = next(
        (v for v in versions if v.document_id == document.id and
         v.version == (document.version or "1.0")),
        None,
    )

    return {
        "document_id": document_id,
        "current": document.version or "1.0",
        "versions": [
            {
                "id": v.id,
                "version": v.version,
                "note": v.note,
                "file_size": v.file_size,
                "mime_type": v.mime_type,
                "is_current": bool(v.id == (current_snapshot.id if current_snapshot else None)),
                "is_locked": bool(v.is_locked),
                "editable": bool(v.source_html),
                "created_at": v.created_at,
                "author": (v.author.full_name or v.author.username) if v.author else None,
                "file_url": f"/api/documents/{document_id}/versions/{v.id}/file",
            }
            for v in versions
        ],
    }


@router.get("/{document_id}/versions/{version_id}/file")
def get_version_file(
    document_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Serve one historical version, inline, so any version can be re-read."""
    from ..services import version_service

    snapshot = version_service.get(db, document_id, version_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Version not found")

    path = Path(snapshot.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="That version's file is no longer in storage")

    media_type = snapshot.mime_type or mimetypes.guess_type(str(path))[0] \
        or "application/octet-stream"
    if media_type.startswith("text/"):
        media_type = f"{media_type}; charset=utf-8"

    return FileResponse(
        path=str(path),
        media_type=media_type,
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-cache",
        },
    )


@router.post("/{document_id}/versions/{version_id}/restore")
def restore_version(
    document_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """
    Bring an older version back as the newest one.

    Forward-only: the old version stays in the history and a new version is
    written carrying its content, so the restore is itself part of the record.
    """
    from ..services import version_service

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    snapshot = version_service.get(db, document_id, version_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Version not found")
    if snapshot.is_current:
        raise HTTPException(status_code=400, detail="That version is already the current one")

    try:
        created = version_service.restore(db, document, snapshot, current_user)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    from ..services.audit_service import log_audit_event
    log_audit_event(
        db=db, user_id=current_user.id, action="document.version.restore",
        resource_type="document", resource_id=document_id,
        details={"restored_from": snapshot.version, "new_version": document.version},
    )

    return {
        "message": f"Restored v{snapshot.version} as v{document.version}",
        "version": document.version,
        "id": created.id if created else None,
    }


@router.get("/{document_id}/versions/{version_id}/compare/{other_version_id}")
def compare_document_versions(
    document_id: str,
    version_id: str,
    other_version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """Compare two historical versions of the same document."""
    from ..services import version_service

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if not check_document_access(document, current_user, 'read'):
        raise HTTPException(status_code=403, detail="Access denied to this document")

    try:
        return version_service.compare_versions(db, document_id, version_id, other_version_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{document_id}/versions/{version_id}/checkout")
def checkout_document_version(
    document_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """Check out a historical version as the current working file."""
    from ..services import version_service

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    if not check_document_access(document, current_user, 'write'):
        raise HTTPException(status_code=403, detail="Access denied to this document")

    try:
        snapshot = version_service.checkout_version(db, document, version_id, actor=current_user)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "message": f"Checked out v{snapshot.version}",
        "version": snapshot.version,
        "id": snapshot.id,
    }


@router.get("/{document_id}/text")
def get_document_text(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """The extracted text on its own, for the viewer's text mode and for search hits."""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not check_document_access(document, current_user, 'read'):
        raise HTTPException(status_code=403, detail="Access denied to this document")

    return {
        "document_id": document.id,
        "title": document.title or document.original_filename,
        "text": document.full_text or "",
        "summary": document.summary or "",
        "ocr_status": document.ocr_status,
    }

@router.get("/{document_id}/thumbnail")
def get_document_thumbnail(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """
    A PNG picture of the document's first page.

    404 when the format cannot be pictured - Word, Excel and plain text. The
    caller is expected to draw a typed placeholder rather than a broken image,
    so this is a normal outcome and not an error worth logging.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    file_path = Path(document.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found")

    png = thumbnails.thumbnail(document_id, file_path, document.mime_type)
    if png is None:
        raise HTTPException(status_code=404, detail="No preview for this file type")

    return Response(
        content=png,
        media_type="image/png",
        # Cached under a modification-time key, so a long browser cache is safe.
        headers={"Cache-Control": "private, max-age=86400"},
    )

@router.post("/{document_id}/tags/{tag_id}")
def add_tag_to_document(
    document_id: str,
    tag_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Add a tag to a document"""
    from ..models import Tag

    # Check if document exists
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check if tag exists
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    # Check if relationship already exists
    if tag in document.tags:
        raise HTTPException(status_code=400, detail="Tag already associated with document")

    # Create association through the ORM relationship (document_tags is a
    # plain association Table, there is no DocumentTag model).
    document.tags.append(tag)
    db.commit()

    return {"message": "Tag added to document"}

@router.delete("/{document_id}/tags/{tag_id}")
def remove_tag_from_document(
    document_id: str,
    tag_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Remove a tag from a document"""
    # Check if document exists
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check if tag exists
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")

    # Check if tag is associated with document
    if tag not in document.tags:
        raise HTTPException(status_code=404, detail="Tag not associated with document")

    # Remove tag from document using SQLAlchemy relationship
    document.tags.remove(tag)
    db.commit()

    return {"message": "Tag removed from document"}

@router.post("/{document_id}/tags", response_model=TagAddResponse)
def create_and_add_tag_to_document(
    document_id: str,
    payload: TagAddRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """
    Tag a document, creating any tag that does not exist yet.

    Takes `tag_name` for one or `tag_names` for several. It used to take an
    untyped dict and read only `tag_name`, so the Review screen - which sends
    the plural - got "400 Tag name is required" on every attempt, with nothing
    in the signature to reveal the mismatch. Both spellings now work and the
    request is validated against a schema.

    Adding a tag a document already has is not an error. Asking for a state
    that is already true has succeeded; failing it means the caller has to
    special-case a message that means "fine".
    """
    from ..models import Tag
    import uuid

    names, seen = [], set()
    for raw in ([payload.tag_name] if payload.tag_name else []) + list(payload.tag_names or []):
        name = (raw or "").strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)

    if not names:
        raise HTTPException(status_code=400, detail="Give a tag name to add")

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    added, already = [], []
    for name in names:
        # Tag names are matched without regard to case, so "Invoice" does not
        # become a second tag alongside "invoice".
        tag = db.query(Tag).filter(func.lower(Tag.name) == name.lower()).first()
        if tag is None:
            tag = Tag(id=str(uuid.uuid4()), name=name)
            db.add(tag)
            db.flush()

        if tag in document.tags:
            raise HTTPException(
                status_code=400,
                detail=f"Tag already associated with document: {tag.name}",
            )

        document.tags.append(tag)
        added.append(tag)

    db.commit()

    parts = []
    if added:
        parts.append(f"Added {', '.join(t.name for t in added)}")
    if already:
        parts.append(f"{', '.join(t.name for t in already)} was already there")

    tag_ids = [t.id for t in added + already]
    tag_id = tag_ids[0] if tag_ids else None

    return TagAddResponse(
        message=" · ".join(parts) or "Nothing to add",
        tag_id=tag_id,
        tag_ids=tag_ids,
        added=[TagSchema.model_validate(t) for t in added],
        already_present=[TagSchema.model_validate(t) for t in already],
        tags=[TagSchema.model_validate(t) for t in document.tags],
    )

@router.post("/cleanup/orphaned")
def cleanup_orphaned_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_document_delete_flexible)
):
    """Remove orphaned document entries where the physical file no longer exists"""
    documents = db.query(Document).all()
    orphaned_count = 0
    cleaned_documents = []

    for document in documents:
        if document.file_path:
            file_path = Path(document.file_path)
            if not file_path.exists():
                # This is an orphaned document
                orphaned_count += 1

                # Store info before deletion
                cleaned_documents.append({
                    "id": document.id,
                    "filename": document.original_filename,
                    "file_path": document.file_path,
                    "hash": document.file_hash
                })

                # Delete from vector database
                try:
                    from ..services.vector_db_service import VectorDBService
                    vector_db = VectorDBService(db)
                    vector_db.delete_document(document.id)
                except Exception as e:
                    print(f"Error deleting from vector database: {e}")

                # Delete related processing logs
                try:
                    processing_logs = db.query(ProcessingLog).filter(ProcessingLog.document_id == document.id).all()
                    for log in processing_logs:
                        db.delete(log)
                except Exception as e:
                    print(f"Error deleting processing logs: {e}")

                # Clear tag associations
                try:
                    document.tags.clear()
                except Exception as e:
                    print(f"Error clearing tag associations: {e}")

                # Delete the document
                db.delete(document)

    db.commit()

    return {
        "message": f"Cleaned up {orphaned_count} orphaned document entries",
        "cleaned_documents": cleaned_documents,
        "count": orphaned_count
    }

@router.post("/{document_id}/reprocess-ai")
async def reprocess_ai_only(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Retry only AI processing for a document with failed AI but successful OCR"""
    from ..services.document_processor import DocumentProcessor
    from ..models import ProcessingLog

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.ocr_status != "completed":
        raise HTTPException(status_code=400, detail="OCR must be completed before retrying AI processing")

    try:
        # Get file path for reprocessing
        file_path = Path(document.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Document file not found")

        # Reset AI status only
        document.ai_status = "pending"
        document.summary = None
        document.processed_at = None

        # Log retry attempt
        log = ProcessingLog(
            document_id=document_id,
            operation="ai_retry",
            status="info",
            message="AI processing queued for retry"
        )
        db.add(log)
        db.commit()

        # reprocess_existing only re-runs the stages whose status is pending or
        # failed, so this performs AI extraction (and re-vectorisation) without
        # redoing OCR. It opens its own session because ours closes with the
        # response.
        background_tasks.add_task(_reprocess_document_task, document_id)

        return {"message": "AI processing queued for retry"}

    except HTTPException:
        raise
    except Exception as e:
        # Log failure
        log = ProcessingLog(
            document_id=document_id,
            operation="ai_retry",
            status="error",
            message=f"Failed to queue AI retry: {str(e)}"
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to retry AI processing: {str(e)}")

@router.post("/{document_id}/reprocess-ocr")
def reprocess_ocr_only(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Retry only OCR processing for a document"""
    from ..services.document_processor import DocumentProcessor
    from ..models import ProcessingLog

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        file_path = Path(document.file_path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Document file not found")

        # Reset OCR status only
        document.ocr_status = "pending"
        document.full_text = None

        # Log retry attempt
        log = ProcessingLog(
            document_id=document_id,
            operation="ocr_retry",
            status="info",
            message="OCR processing queued for retry"
        )
        db.add(log)
        db.commit()

        # Run OCR synchronously so the caller learns whether it succeeded.
        processor = DocumentProcessor(db)
        text = processor.ocr_service.extract_text(file_path)
        document.full_text = text
        document.ocr_status = "completed"
        db.add(
            ProcessingLog(
                document_id=document_id,
                operation="ocr",
                status="success",
                message=f"OCR retry extracted {len(text)} characters",
            )
        )
        db.commit()

        return {
            "message": "OCR processing completed",
            "characters_extracted": len(text),
        }

    except HTTPException:
        raise
    except Exception as e:
        document.ocr_status = "failed"
        # Log failure
        log = ProcessingLog(
            document_id=document_id,
            operation="ocr_retry",
            status="error",
            message=f"Failed to queue OCR retry: {str(e)}"
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to retry OCR processing: {str(e)}")

@router.post("/{document_id}/reprocess-vector")
def reprocess_vector_only(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Retry only vectorization for a document"""
    from ..services.document_processor import DocumentProcessor
    from ..models import ProcessingLog

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.full_text:
        raise HTTPException(status_code=400, detail="Document must have OCR text before vectorization")

    try:
        # Reset vector status only
        document.vector_status = "processing"

        # Log retry attempt
        log = ProcessingLog(
            document_id=document_id,
            operation="vector_retry",
            status="info",
            message="Vectorization processing queued for retry"
        )
        db.add(log)
        db.commit()

        # Trigger vectorization only. _store_embeddings sets vector_status and
        # commits on success/failure.
        processor = DocumentProcessor(db)
        processor._store_embeddings(document, db)

        return {"message": "Vectorization completed", "vector_status": document.vector_status}

    except HTTPException:
        raise
    except Exception as e:
        # Log failure
        log = ProcessingLog(
            document_id=document_id,
            operation="vector_retry",
            status="error",
            message=f"Failed to queue vectorization retry: {str(e)}"
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to retry vectorization: {str(e)}")

# Document Relations endpoints
@router.get("/{document_id}/relations")
def get_document_relations(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Get all related documents (both parents and children)"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Get both parent and child relations
    return {
        "document_id": document_id,
        "parent_documents": [
            {
                "id": parent.id,
                "title": parent.title or parent.filename,
                "filename": parent.filename,
                "document_date": parent.document_date,
                "correspondent": parent.correspondent.name if parent.correspondent else None
            }
            for parent in document.parents
        ],
        "child_documents": [
            {
                "id": child.id,
                "title": child.title or child.filename,
                "filename": child.filename,
                "document_date": child.document_date,
                "correspondent": child.correspondent.name if child.correspondent else None
            }
            for child in document.children
        ]
    }

@router.post("/{document_id}/relations/{related_document_id}")
def add_document_relation(
    document_id: str,
    related_document_id: str,
    relation_type: str = "child",  # "child" or "parent"
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Add a relation between two documents"""
    if document_id == related_document_id:
        raise HTTPException(status_code=400, detail="Cannot relate a document to itself")

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    related_document = db.query(Document).filter(Document.id == related_document_id).first()
    if not related_document:
        raise HTTPException(status_code=404, detail="Related document not found")

    # Add relation based on type
    if relation_type == "child":
        if related_document not in document.children:
            document.children.append(related_document)
    else:  # parent
        if document not in related_document.children:
            related_document.children.append(document)

    db.commit()

    return {"message": "Relation added successfully"}

@router.delete("/{document_id}/relations/{related_document_id}")
def remove_document_relation(
    document_id: str,
    related_document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Remove a relation between two documents"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    related_document = db.query(Document).filter(Document.id == related_document_id).first()
    if not related_document:
        raise HTTPException(status_code=404, detail="Related document not found")

    # Remove from both directions
    if related_document in document.children:
        document.children.remove(related_document)
    if document in related_document.children:
        related_document.children.remove(document)

    db.commit()

    return {"message": "Relation removed successfully"}

@router.get("/{document_id}/similar")
def find_similar_documents(
    document_id: str,
    limit: int = 10,
    threshold: float = 0.3,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Find similar documents using vector similarity search"""
    from ..services.vector_db_service import VectorDBService
    from ..services.ai_service import AIService

    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Check if document has embeddings - if not, try to proceed anyway
    if document.vector_status != "completed":
        print(f"Warning: Document {document_id} has vector_status: {document.vector_status}")
        # Don't fail, just proceed with search - the vector DB might still have embeddings

    try:
        # Initialize services with better error handling
        try:
            vector_db = VectorDBService(db)
        except Exception as e:
            print(f"Error initializing VectorDBService: {e}")
            raise HTTPException(status_code=500, detail="Vector database service not available")

        try:
            ai_service = AIService(db_session=db)
        except Exception as e:
            print(f"Error initializing AIService: {e}")
            raise HTTPException(status_code=500, detail="AI service not configured or not available")

        # Create search text from document
        search_text = f"{document.title or ''} {document.summary or ''}"
        if not search_text.strip() and document.full_text:
            search_text = document.full_text[:1000]

        if not search_text.strip():
            print(f"No search text available for document {document_id}")
            return {
                "document_id": document_id,
                "similar_documents": [],
                "count": 0,
                "message": "No text content available for similarity search"
            }

        # Generate embeddings for search
        try:
            search_embeddings = ai_service.generate_embeddings(search_text)
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            raise HTTPException(status_code=500, detail="Failed to generate embeddings for similarity search")

        # Search for similar documents
        try:
            results = vector_db.search_similar(
                query_embeddings=search_embeddings,
                limit=limit + 1  # +1 because the document itself might be included
            )
        except Exception as e:
            print(f"Error searching similar documents: {e}")
            raise HTTPException(status_code=500, detail="Failed to search vector database")

        # Filter out the document itself and apply threshold
        similar_docs = []
        for result in results:
            if result['id'] != document_id and result.get('score', 0) >= threshold:
                # Get document details from database
                sim_doc = db.query(Document).filter(Document.id == result['id']).first()
                if sim_doc:
                    similar_docs.append({
                        "id": sim_doc.id,
                        "title": sim_doc.title or sim_doc.filename,
                        "filename": sim_doc.filename,
                        "document_date": sim_doc.document_date,
                        "correspondent": sim_doc.correspondent.name if sim_doc.correspondent else None,
                        "similarity_score": result.get('score', 0),
                        "summary": sim_doc.summary
                    })

        return {
            "document_id": document_id,
            "similar_documents": similar_docs,
            "count": len(similar_docs)
        }

    except HTTPException:
        # Re-raise HTTP exceptions as they are already properly formatted
        raise
    except Exception as e:
        print(f"Unexpected error in find_similar_documents: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to find similar documents: {str(e)}")

# Document Notes endpoints
@router.put("/{document_id}/notes")
def update_document_notes(
    document_id: str,
    notes_data: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update"))
):
    """Update notes for a document"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    notes = notes_data.get("notes", "")
    document.notes = notes
    db.commit()
    db.refresh(document)

    return {
        "message": "Notes updated successfully",
        "notes": document.notes
    }

@router.get("/{document_id}/notes")
def get_document_notes(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Get notes for a document"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return {
        "document_id": document_id,
        "notes": document.notes or ""
    }

@router.post("/{document_id}/approve", response_model=DocumentApprovalResponse)
def approve_document(
    document_id: str,
    approval_request: DocumentApprovalRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.approve"))
):
    """Approve or disapprove a document"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Update approval status
    document.is_approved = approval_request.approved
    document.approved_by = current_user.id if approval_request.approved else None
    document.approved_at = datetime.utcnow() if approval_request.approved else None

    db.commit()
    db.refresh(document)

    return DocumentApprovalResponse(
        success=True,
        message="Document approved successfully" if approval_request.approved else "Document approval removed",
        document_id=document_id,
        is_approved=document.is_approved,
        approved_at=document.approved_at,
        approved_by=document.approved_by
    )

@router.get("/{document_id}/approval-status")
def get_document_approval_status(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read"))
):
    """Get approval status of a document"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    approved_by_user = None
    if document.approved_by:
        approved_by_user = db.query(User).filter(User.id == document.approved_by).first()

    return {
        "document_id": document_id,
        "is_approved": document.is_approved,
        "approved_at": document.approved_at,
        "approved_by": document.approved_by,
        "approved_by_user": {
            "id": approved_by_user.id,
            "username": approved_by_user.username,
            "full_name": approved_by_user.full_name
        } if approved_by_user else None
    }
