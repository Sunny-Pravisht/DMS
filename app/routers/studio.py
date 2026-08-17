"""
The Document Studio API: everything behind creating and editing a document.

The shape of it follows the way the screen works:

    templates   what paper to write on
    assets      what images can go on it
    ai          rewrite, summarise, correct, draft
    drafts      work that is not finished
    preview     see the PDF without committing to it
    publish     file it in the repository as a real Document

Publishing is the interesting one. It does not invent a second ingest path: it
renders a PDF, writes it into the same storage tree the file watcher uses,
creates the same `Document` row, and hands the same enrichment work to the same
background pipeline. A composed document is a first-class document from the
moment it is saved - searchable, routable, retainable, no different from a scan.
"""
from __future__ import annotations

import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..utils import ist
from ..config import get_settings
from ..database import get_db
from ..models import Correspondent, Document, DocumentDraft, DocType, Tag, User
from ..services import authoring_ai, doc_templates, media_service
from ..services.auth_service import get_current_user_flexible, require_permission_flexible
from ..services.pdf_render import RenderError, html_to_text, page_estimate, render_pdf, sanitize_html
from ..utils.file_security import calculate_file_hash, set_secure_permissions

router = APIRouter()

MAX_BODY_CHARS = 900_000  # a very long document is ~200k; this is the abuse ceiling


# --------------------------------------------------------------- payloads


class DraftPayload(BaseModel):
    title: str = Field(default="Untitled document", max_length=300)
    template_id: Optional[str] = None
    html: str = ""
    meta: dict = Field(default_factory=dict)
    source_document_id: Optional[str] = None


class RenderPayload(BaseModel):
    title: str = Field(default="Document", max_length=300)
    template_id: Optional[str] = None
    html: str = ""


class PublishPayload(BaseModel):
    title: str = Field(default="Untitled document", max_length=300)
    template_id: Optional[str] = None
    html: str = ""
    meta: dict = Field(default_factory=dict)
    draft_id: Optional[str] = None
    source_document_id: Optional[str] = None


class AIPayload(BaseModel):
    action: str
    text: str = ""
    instruction: Optional[str] = None
    target: Optional[str] = None
    title: Optional[str] = None


# ------------------------------------------------------------- templates


@router.get("/templates")
def list_templates(
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """Every letterhead the Studio can print on, with its full spec."""
    return {
        "templates": doc_templates.all_templates(),
        "default": doc_templates.DEFAULT_TEMPLATE_ID,
    }


@router.get("/templates/{template_id}/starter")
def template_starter(
    template_id: str,
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """The first draft offered when this template is picked on a blank page."""
    if not doc_templates.exists(template_id):
        raise HTTPException(status_code=404, detail="No such template")
    today = ist.now().strftime(ist.DATE_LONG)
    return {
        "template_id": template_id,
        "html": doc_templates.starter_html(template_id, today),
    }


# ---------------------------------------------------------------- assets


@router.get("/assets")
def list_assets(
    kind: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """The image library: shipped marks plus this user's own uploads."""
    media_service.seed_builtins(db)
    assets = media_service.list_assets(db, current_user, kind)
    return {
        "assets": [
            {
                "id": a.id,
                "key": a.key,
                "name": a.name,
                "kind": a.kind,
                "url": f"/api/studio/assets/{a.id}/file",
                # The web canvas prefers the SVG for a built-in, since it stays
                # crisp at any zoom - but only where one exists. Real supplied
                # artwork is raster, so those fall back to the stored file.
                "web_url": (
                    f"{doc_templates.BRAND_WEB}/{a.key}.svg"
                    if a.is_builtin and a.key
                    and (doc_templates.BRAND_DIR / f"{a.key}.svg").exists()
                    else f"/api/studio/assets/{a.id}/file"
                ),
                "builtin": a.is_builtin,
                "size": a.file_size,
            }
            for a in assets
        ]
    }


@router.get("/assets/{asset_id}/file")
def get_asset_file(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """Serve one image from the library."""
    asset = media_service.get_asset(db, asset_id, current_user)
    if not asset:
        raise HTTPException(status_code=404, detail="Image not found")

    path = Path(asset.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image file is missing from storage")

    return FileResponse(
        path=str(path),
        media_type=asset.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.post("/assets")
async def upload_asset(
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    kind: str = Form("image"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.create")),
):
    """Add an image from the user's own machine to their library."""
    content = await file.read()
    try:
        asset = media_service.store_upload(db, current_user, file.filename or "", content,
                                           name=name, kind=kind)
    except media_service.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "id": asset.id,
        "name": asset.name,
        "kind": asset.kind,
        "url": f"/api/studio/assets/{asset.id}/file",
        "web_url": f"/api/studio/assets/{asset.id}/file",
        "builtin": False,
        "size": asset.file_size,
    }


@router.delete("/assets/{asset_id}")
def delete_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.create")),
):
    asset = media_service.get_asset(db, asset_id, current_user)
    if not asset:
        raise HTTPException(status_code=404, detail="Image not found")
    if not current_user.is_admin and asset.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="That image is not yours to delete")
    try:
        media_service.delete_asset(db, asset)
    except media_service.MediaError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Image removed"}


# -------------------------------------------------------------------- AI


@router.get("/ai/actions")
def ai_actions(current_user: User = Depends(require_permission_flexible("documents.read"))):
    """What "Edit with AI" can do, so the menu is never out of step with the API."""
    return {"actions": authoring_ai.available_actions()}


@router.post("/ai")
def run_ai(
    payload: AIPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """Run one editing action over the selection, or the whole body."""
    if len(payload.text or "") > MAX_BODY_CHARS:
        raise HTTPException(status_code=413, detail="That document is too long to edit with AI.")
    try:
        return authoring_ai.run(
            db,
            action=payload.action,
            text=payload.text,
            instruction=payload.instruction,
            target=payload.target,
            title=payload.title,
        )
    except authoring_ai.AuthoringError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------------------------------------------------------------- drafts


def _draft_json(draft: DocumentDraft) -> dict:
    try:
        meta = json.loads(draft.meta) if draft.meta else {}
    except (TypeError, ValueError):
        meta = {}
    return {
        "id": draft.id,
        "title": draft.title,
        "template_id": draft.template_id,
        "html": draft.html or "",
        "meta": meta,
        "document_id": draft.document_id,
        "source_document_id": draft.source_document_id,
        "status": draft.status,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "pages": page_estimate(draft.html or ""),
    }


@router.get("/drafts")
def list_drafts(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """This user's unfinished documents, newest first."""
    drafts = (
        db.query(DocumentDraft)
        .filter(DocumentDraft.owner_id == current_user.id, DocumentDraft.status == "draft")
        .order_by(DocumentDraft.updated_at.desc())
        .limit(30)
        .all()
    )
    return {"drafts": [_draft_json(d) for d in drafts]}


@router.post("/drafts")
def create_draft(
    payload: DraftPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.create")),
):
    if len(payload.html or "") > MAX_BODY_CHARS:
        raise HTTPException(status_code=413, detail="That document is too large to save.")

    draft = DocumentDraft(
        owner_id=current_user.id,
        title=(payload.title or "Untitled document").strip()[:300],
        template_id=payload.template_id,
        html=sanitize_html(payload.html),
        meta=json.dumps(payload.meta or {}),
        source_document_id=payload.source_document_id,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return _draft_json(draft)


@router.get("/drafts/{draft_id}")
def get_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    draft = _own_draft(db, draft_id, current_user)
    return _draft_json(draft)


@router.put("/drafts/{draft_id}")
def update_draft(
    draft_id: str,
    payload: DraftPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.create")),
):
    """Autosave target. Called often, so it does the least work it can."""
    if len(payload.html or "") > MAX_BODY_CHARS:
        raise HTTPException(status_code=413, detail="That document is too large to save.")

    draft = _own_draft(db, draft_id, current_user)
    draft.title = (payload.title or draft.title).strip()[:300]
    draft.template_id = payload.template_id or draft.template_id
    draft.html = sanitize_html(payload.html)
    draft.meta = json.dumps(payload.meta or {})
    if payload.source_document_id:
        draft.source_document_id = payload.source_document_id
    db.commit()
    db.refresh(draft)
    return _draft_json(draft)


@router.delete("/drafts/{draft_id}")
def delete_draft(
    draft_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.create")),
):
    draft = _own_draft(db, draft_id, current_user)
    db.delete(draft)
    db.commit()
    return {"message": "Draft discarded"}


def _own_draft(db: Session, draft_id: str, user: User) -> DocumentDraft:
    draft = db.query(DocumentDraft).filter(DocumentDraft.id == draft_id).first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.owner_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="That draft belongs to someone else")
    return draft


# ----------------------------------------------------------- open for edit


@router.get("/source/{document_id}")
def get_editable_source(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """
    What the Studio should load when someone presses Edit on a document.

    A document written here comes back exactly as it was written. One that
    arrived as a scan or a PDF has no editable source, so its extracted text is
    offered instead - flagged honestly, because turning OCR output into a body
    is a conversion, not a round trip. Storage-only My Folder uploads are a small
    exception: when the backing file is itself plain text, the Studio can safely
    open that text without triggering the OCR/AI pipeline.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.source_html:
        return {
            "document_id": document.id,
            "title": document.title or document.original_filename,
            "template_id": document.template_id or doc_templates.DEFAULT_TEMPLATE_ID,
            "html": document.source_html,
            "lossless": True,
            "origin": document.origin or "composed",
            "version": document.version or "1.0",
            "meta": _document_meta(document),
        }

    text = (document.full_text or document.summary or "").strip()
    if not text:
        file_path = Path(document.file_path) if document.file_path else None
        if file_path and file_path.exists():
            mime = (document.mime_type or "").lower()
            suffix = file_path.suffix.lower()
            if mime.startswith("text/") or suffix in {".txt", ".md", ".markdown", ".csv", ".log"}:
                try:
                    text = file_path.read_text(encoding="utf-8", errors="replace").strip()
                except Exception:
                    text = ""

    html = _text_to_html(text) if text else "<p></p>"
    lossless = bool(document.source_html)

    return {
        "document_id": document.id,
        "title": document.title or document.original_filename,
        "template_id": doc_templates.DEFAULT_TEMPLATE_ID,
        "html": html,
        "lossless": lossless,
        "origin": document.origin or "uploaded",
        "version": document.version or "1.0",
        "meta": _document_meta(document),
        "notice": (
            "This document arrived as a file, so there is no editable original. "
            "The text read from it has been laid out for you to edit. Saving "
            "creates a new version and leaves the original file untouched."
        ) if not lossless else None,
    }


def _document_meta(document: Document) -> dict:
    return {
        "doctype_id": document.doctype_id,
        "doctype_name": document.doctype.name if document.doctype else "",
        "correspondent_id": document.correspondent_id,
        "correspondent_name": document.correspondent.name if document.correspondent else "",
        "document_date": document.document_date.isoformat() if document.document_date else None,
        "tags": [t.name for t in (document.tags or [])],
    }


def _text_to_html(text: str) -> str:
    """Lay extracted text out as paragraphs so it is editable, not a wall."""
    from ..services.doc_templates import _esc

    blocks = [b.strip() for b in text.replace("\r\n", "\n").split("\n\n") if b.strip()]
    if not blocks:
        return "<p></p>"
    return "".join(
        "<p>" + _esc(b).replace("\n", "<br>") + "</p>" for b in blocks[:400]
    )


# --------------------------------------------------------------- preview


@router.post("/preview")
def preview_pdf(
    payload: RenderPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """Render the document without saving anything. Used by Preview and Download."""
    if len(payload.html or "") > MAX_BODY_CHARS:
        raise HTTPException(status_code=413, detail="That document is too large to render.")

    try:
        pdf = render_pdf(
            html=payload.html,
            template_id=payload.template_id,
            title=payload.title or "Document",
            author=current_user.full_name or current_user.username,
            asset_resolver=media_service.resolver(db, current_user),
        )
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    filename = _safe_filename(payload.title or "document")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )


# --------------------------------------------------------------- publish


@router.post("/publish")
def publish(
    payload: PublishPayload,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.create")),
):
    """
    File a composed document in the repository.

    Renders the PDF, writes it into the storage tree, creates the Document row,
    then hands classification and indexing to the background so the author is
    not left waiting on a model call.
    """
    body = payload.html or ""
    if len(body) > MAX_BODY_CHARS:
        raise HTTPException(status_code=413, detail="That document is too large to publish.")

    title = (payload.title or "Untitled document").strip()[:300] or "Untitled document"
    clean_html = sanitize_html(body)
    text = html_to_text(clean_html)

    if not text.strip():
        raise HTTPException(status_code=400, detail="There is nothing in this document to save.")

    template_id = payload.template_id if doc_templates.exists(payload.template_id) else \
        doc_templates.DEFAULT_TEMPLATE_ID

    try:
        pdf = render_pdf(
            html=clean_html,
            template_id=template_id,
            title=title,
            author=current_user.full_name or current_user.username,
            asset_resolver=media_service.resolver(db, current_user),
        )
    except RenderError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    meta = payload.meta or {}
    source = None
    if payload.source_document_id:
        source = db.query(Document).filter(Document.id == payload.source_document_id).first()

    # ---- where the file lives -------------------------------------------
    correspondent = _resolve_correspondent(db, meta)
    document_date = _resolve_date(meta)

    settings = get_settings(db)
    folder = _folder_name(correspondent.name if correspondent else "HARMAN Internal")
    target_dir = Path(settings.storage_folder) / folder / document_date.strftime("%Y-%m-%d")
    target_dir.mkdir(parents=True, exist_ok=True)

    document = Document(
        filename="",
        original_filename=f"{_safe_filename(title)}.pdf",
        file_hash="",
        file_path="",
        file_size=len(pdf),
        mime_type="application/pdf",
        title=title,
        full_text=text,
        document_date=document_date,
        origin="composed",
        template_id=template_id,
        source_html=clean_html,
        created_by=current_user.id,
        # The body is authoritative, so there is nothing left for OCR to read.
        ocr_status="completed",
        ai_status="pending",
        vector_status="pending",
    )

    if source:
        document.revision_of = source.id
        document.version = _next_version(source.version)
    else:
        document.version = "1.0"

    db.add(document)
    db.commit()
    db.refresh(document)

    path = target_dir / f"{document.id}_{_safe_filename(title)}.pdf"
    try:
        path.write_bytes(pdf)
        set_secure_permissions(path, is_private=True)
    except OSError as exc:
        db.delete(document)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Could not write the document: {exc}")

    document.file_path = str(path)
    document.filename = path.name
    document.file_hash = calculate_file_hash(path)
    document.processed_at = datetime.utcnow()

    _apply_meta(db, document, meta, correspondent)

    if source:
        # Keep the chain navigable from either end.
        if document not in source.children:
            source.children.append(document)

    db.commit()
    db.refresh(document)

    # Record the version at the moment it was written, so the history has the
    # bytes as filed rather than whatever the file becomes after the next edit.
    from ..services import version_service
    version_service.capture(
        db, document, author=current_user,
        version=document.version,
        note=(f"Revised from v{source.version or '1.0'}" if source
              else "Written in the Document Studio"),
    )

    if payload.draft_id:
        draft = db.query(DocumentDraft).filter(DocumentDraft.id == payload.draft_id).first()
        if draft and (draft.owner_id == current_user.id or current_user.is_admin):
            draft.status = "published"
            draft.document_id = document.id
            db.commit()

    _audit(db, current_user, document, source)

    background_tasks.add_task(_enrich, document.id)

    return {
        "id": document.id,
        "title": document.title,
        "version": document.version,
        "revision_of": document.revision_of,
        "pages": page_estimate(clean_html),
        "file_size": document.file_size,
        "url": f"/documents/detail?id={document.id}",
        "message": (
            f"Version {document.version} saved as a new version of the original"
            if source else "Document saved to the repository"
        ),
    }


# ---------------------------------------------------------------- helpers


def _resolve_correspondent(db: Session, meta: dict) -> Optional[Correspondent]:
    """Use the chosen correspondent, or create one from a typed name."""
    corr_id = (meta.get("correspondent_id") or "").strip()
    if corr_id:
        found = db.query(Correspondent).filter(Correspondent.id == corr_id).first()
        if found:
            return found

    name = (meta.get("correspondent_name") or "").strip()
    if not name:
        return None

    existing = db.query(Correspondent).filter(Correspondent.name == name).first()
    if existing:
        return existing

    created = Correspondent(name=name[:120])
    db.add(created)
    db.commit()
    db.refresh(created)
    return created


def _resolve_date(meta: dict) -> datetime:
    raw = (meta.get("document_date") or "").strip()
    if raw:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(raw[:len(fmt) + 2].rstrip("Z"), fmt)
            except ValueError:
                continue
    return datetime.now()


def _apply_meta(db: Session, document: Document, meta: dict, correspondent):
    if correspondent:
        document.correspondent_id = correspondent.id

    doctype_id = (meta.get("doctype_id") or "").strip()
    doctype_name = (meta.get("doctype_name") or "").strip()

    if doctype_id:
        if db.query(DocType).filter(DocType.id == doctype_id).first():
            document.doctype_id = doctype_id
    elif doctype_name:
        doctype = db.query(DocType).filter(DocType.name == doctype_name).first()
        if not doctype:
            doctype = DocType(name=doctype_name[:80])
            db.add(doctype)
            db.commit()
            db.refresh(doctype)
        document.doctype_id = doctype.id

    notes = []
    if meta.get("department"):
        notes.append(f"Department: {meta['department']}")
    if meta.get("sensitivity"):
        notes.append(f"Sensitivity: {meta['sensitivity']}")
    if notes:
        document.notes = "\n".join(notes)

    for name in (meta.get("tags") or [])[:12]:
        name = str(name).strip()[:60]
        if not name:
            continue
        tag = db.query(Tag).filter(Tag.name == name).first()
        if not tag:
            tag = Tag(name=name)
            db.add(tag)
            db.commit()
            db.refresh(tag)
        if tag not in document.tags:
            document.tags.append(tag)


def _next_version(current: Optional[str]) -> str:
    try:
        major, minor = (current or "1.0").split(".")[:2]
        return f"{int(major)}.{int(minor) + 1}"
    except (ValueError, TypeError):
        return "1.1"


def _folder_name(name: str) -> str:
    import re

    cleaned = re.sub(r'[<>:"/\\|?*]', "_", name).strip(" .")
    return (cleaned[:50].rstrip() or "HARMAN Internal")


def _safe_filename(title: str) -> str:
    import re

    cleaned = re.sub(r"[^A-Za-z0-9 _-]+", "", title).strip().replace(" ", "_")
    return (cleaned[:80] or "document")


def _audit(db: Session, user: User, document: Document, source: Optional[Document]):
    try:
        from ..services.audit_service import log_audit_event

        log_audit_event(
            db=db,
            user_id=user.id,
            action="document.compose" if not source else "document.revise",
            resource_type="document",
            resource_id=document.id,
            details={
                "title": document.title,
                "template": document.template_id,
                "version": document.version,
                "revision_of": document.revision_of,
                "size": document.file_size,
            },
        )
    except Exception as exc:  # auditing must never block the save
        logger.warning(f"Could not write the audit entry for {document.id}: {exc}")


def _enrich(document_id: str):
    """
    Classify and index a freshly composed document, off the request path.

    Failures are recorded on the document rather than raised: a document that
    is saved but not yet classified is a normal state the UI already shows.
    """
    from ..database import SessionLocal

    db = SessionLocal()
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            return

        from ..services.document_processor import DocumentProcessor

        processor = DocumentProcessor(db)

        # Classification: only fill in what the author left blank. Their choices
        # win over the model's; the model is here to save typing, not to argue.
        if processor.ai_service and document.full_text:
            try:
                document.ai_status = "processing"
                db.commit()

                extracted = processor.ai_service.extract_document_metadata(
                    document.full_text, document.original_filename
                )
                if extracted:
                    if not document.summary:
                        document.summary = extracted.summary
                    if not document.doctype_id and extracted.doctype_name:
                        document.doctype_id = processor._get_or_create_doctype(
                            extracted.doctype_name, db).id
                    if not document.correspondent_id and extracted.correspondent_name:
                        document.correspondent_id = processor._get_or_create_correspondent(
                            extracted.correspondent_name, db).id
                    for tag_name in (extracted.tag_names or [])[:8]:
                        tag = processor._get_or_create_tag(tag_name, db)
                        if tag not in document.tags:
                            document.tags.append(tag)
                document.ai_status = "completed"
                db.commit()
            except Exception as exc:
                logger.warning(f"Composed document {document_id}: classification failed: {exc}")
                document.ai_status = "failed"
                db.commit()
        else:
            document.ai_status = "skipped"
            db.commit()

        try:
            processor._store_embeddings(document, db)
            db.commit()
        except Exception as exc:
            logger.warning(f"Composed document {document_id}: indexing failed: {exc}")
            document.vector_status = "failed"
            db.commit()

    except Exception as exc:
        logger.exception(f"Enrichment failed for composed document {document_id}: {exc}")
    finally:
        db.close()
