"""
Step 5: publishing and export.

Publishing is the end of the line, and it is earned: only a document whose
approval chain completed can be published. That single rule is what makes the
publish queue meaningful - everything in it has been through the process, and
nothing can jump it.

Export offers the three shapes a manufacturing business actually needs:

    pdf    the document as filed, letterhead and all - what you print and send
    docx   the editable text, for someone who must revise it in Word
    txt    the plain content, for a system that only wants the words

Only the PDF is the document of record. That is stated on the screen too,
because an exported .docx that lost its letterhead should never be mistaken for
the signed original.
"""
from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..utils import ist
from ..database import get_db
from ..models import ApprovalWorkflow, Document, User, WorkflowEvent
from ..services import version_service, workflow_service as wf
from ..services.auth_service import require_permission_flexible
from ..services.docx_render import html_to_plain, render_docx
from ..services.pdf_render import RenderError, html_to_text, render_pdf

router = APIRouter()

FORMATS = {
    "pdf": ("application/pdf", ".pdf"),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx"),
    "txt": ("text/plain; charset=utf-8", ".txt"),
}


# ------------------------------------------------------------------- queue


@router.get("/queue")
def publish_queue(
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """
    What is ready to publish, and what already went out.

    Both lists on one call: the person doing this job wants to see the queue and
    confirm the last release in the same glance.
    """
    def rows(status: str, limit: int = 60):
        query = (
            db.query(ApprovalWorkflow)
            .join(Document, ApprovalWorkflow.document_id == Document.id)
            .filter(ApprovalWorkflow.status == status)
        )
        if q:
            from sqlalchemy import func, or_
            needle = f"%{q.strip().lower()}%"
            query = query.filter(or_(
                func.lower(Document.title).like(needle),
                func.lower(Document.original_filename).like(needle),
            ))
        order = (ApprovalWorkflow.published_at.desc() if status == wf.PUBLISHED
                 else ApprovalWorkflow.completed_at.desc())
        return query.order_by(order).limit(limit).all()

    from .workflow import _workflow_json

    ready = rows(wf.APPROVED)
    published = rows(wf.PUBLISHED, 30)

    return {
        "ready": [_workflow_json(w, current_user, with_events=False) for w in ready],
        "published": [_workflow_json(w, current_user, with_events=False) for w in published],
        "ready_count": len(ready),
        "published_count": len(published),
    }


@router.post("/{workflow_id}/publish")
def publish(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """Release an approved document, and lock the version that was signed."""
    workflow = wf.load(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Approval process not found")

    try:
        workflow = wf.publish(db, workflow, current_user)
    except wf.WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    document = db.query(Document).filter(Document.id == workflow.document_id).first()
    stamped = 0

    if document:
        # Freeze the bytes and version that approvers reviewed before applying
        # publication-only signature stamps. Updating this snapshot after
        # stamping replaces the approved content with the published rendition;
        # because both snapshots then share the same source HTML, comparison
        # incorrectly reports that nothing changed.
        version_service.lock_current(
            db, document,
            note=(f"Approved v{document.version or '1.0'} · "
                  f"{len([s for s in workflow.steps if s.status == wf.APPROVED])} approver(s)"),
            update_file=False,
        )

        # Stamp the signatures on if any and update only the live published file.
        # The document version established before publication is not bumped.
        stamped = _apply_signatures(db, workflow, document, current_user)

    try:
        from ..services.audit_service import log_audit_event
        log_audit_event(
            db=db, user_id=current_user.id, action="document.publish",
            resource_type="document", resource_id=workflow.document_id,
            details={
                "workflow_id": workflow.id,
                "version": document.version if document else None,
                "title": document.title if document else None,
                "signatures_stamped": stamped,
            },
        )
    except Exception:
        pass

    from .workflow import _workflow_json
    return {
        "message": ("Published with " + str(stamped) +
                    (" signature" if stamped == 1 else " signatures") + " on the document")
                   if stamped else "Published",
        "signatures_stamped": stamped,
        "workflow": _workflow_json(wf.load(db, workflow.id), current_user),
    }


def _apply_signatures(db: Session, workflow, document: Document, actor: User) -> int:
    """
    Write the signed rendition and make it the current version.

    Returns how many signatures were stamped. Anything that is not a PDF, or
    that collected no signatures, is published exactly as it is - that is a
    normal outcome, not a failure, and it must not block the release.
    """
    from ..services import signature_stamp as stamp

    blocks = stamp.blocks_from_workflow(workflow)
    if not blocks:
        return 0

    path = Path(document.file_path) if document.file_path else None
    if not path or not path.exists():
        return 0
    if not (document.mime_type or "").endswith("pdf") and path.suffix.lower() != ".pdf":
        return 0

    try:
        signed = stamp.stamp(path.read_bytes(), blocks, title=document.title or "")
    except stamp.StampError as exc:
        # Publishing is the point of the exercise; a stamping failure should
        # not undo it. Release the unsigned document and say so in the log.
        from loguru import logger
        logger.error(f"Could not stamp signatures on {document.id}: {exc}")
        return 0

    signed_path = path.with_name(f"{path.stem}_signed{path.suffix}")
    signed_path.write_bytes(signed)

    from ..utils.file_security import calculate_file_hash, set_secure_permissions
    set_secure_permissions(signed_path, is_private=True)

    document.file_path = str(signed_path)
    document.filename = signed_path.name
    document.file_size = len(signed)
    document.file_hash = calculate_file_hash(signed_path)
    # The version established at the initial stage is preserved (do not bump at publish time)
    db.commit()

    return len(blocks)


@router.post("/{workflow_id}/unpublish")
def unpublish(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """Withdraw a release. The approval itself stands; only publication is undone."""
    workflow = wf.load(db, workflow_id)
    if not workflow or workflow.status != wf.PUBLISHED:
        raise HTTPException(status_code=404, detail="That document is not published")

    workflow.status = wf.APPROVED
    workflow.published_at = None
    workflow.published_by = None
    db.add(WorkflowEvent(
        workflow_id=workflow.id,
        actor_id=current_user.id,
        kind="cancelled",
        summary=f"{current_user.full_name or current_user.username} withdrew the publication",
    ))
    db.commit()
    return {"message": "Publication withdrawn"}


# ------------------------------------------------------------------ export


@router.get("/export/{document_id}")
def export_document(
    document_id: str,
    format: str = Query(default="pdf"),
    version_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """
    Export a document in one of the supported formats.

    A PDF that already exists on disk is served as-is rather than re-rendered:
    the bytes that were approved are the bytes that go out. Only formats that
    have to be generated (docx, txt) are built on the fly, and only when the
    document has an editable body to build them from.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    fmt = (format or "pdf").lower()
    if fmt not in FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"'{format}' is not an export format. Use pdf, docx or txt.",
        )

    media_type, suffix = FORMATS[fmt]
    stem = _safe_name(document.title or document.original_filename or "document")

    source_html = document.source_html
    if version_id:
        snapshot = version_service.get(db, document_id, version_id)
        if not snapshot:
            raise HTTPException(status_code=404, detail="That version does not exist")
        source_html = snapshot.source_html or source_html
        if fmt == "pdf" and Path(snapshot.file_path).exists():
            return FileResponse(
                path=snapshot.file_path,
                media_type="application/pdf",
                filename=f"{stem}_v{snapshot.version}.pdf",
            )

    # ---- PDF -------------------------------------------------------------
    if fmt == "pdf":
        path = Path(document.file_path) if document.file_path else None
        if path and path.exists() and (document.mime_type or "").endswith("pdf"):
            return FileResponse(path=str(path), media_type="application/pdf",
                                filename=f"{stem}.pdf")

        if not source_html:
            # A scan or an Office file has no body to re-render. Hand back the
            # original rather than inventing a PDF that is not the document.
            if path and path.exists():
                guessed = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
                return FileResponse(path=str(path), media_type=guessed,
                                    filename=document.original_filename)
            raise HTTPException(status_code=404, detail="The document file is missing")

        try:
            from ..services import media_service
            pdf = render_pdf(
                html=source_html,
                template_id=document.template_id,
                title=document.title or stem,
                author=current_user.full_name or current_user.username,
                asset_resolver=media_service.resolver(db, current_user),
            )
        except RenderError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return Response(content=pdf, media_type=media_type, headers=_attach(stem, suffix))

    # ---- DOCX / TXT ------------------------------------------------------
    body = source_html
    if not body:
        text = (document.full_text or "").strip()
        if not text:
            raise HTTPException(
                status_code=400,
                detail="This document has no text to export. Download the original file instead.",
            )
        body = "".join(f"<p>{_esc(p)}</p>" for p in text.split("\n\n") if p.strip())

    if fmt == "docx":
        data = render_docx(
            body,
            title=document.title or stem,
            author=current_user.full_name or current_user.username,
            subtitle=f"Exported from HARMAN DMS · v{document.version or '1.0'} · "
                     f"{ist.now().strftime(ist.DATE_LONG)}",
        )
        return Response(content=data, media_type=media_type, headers=_attach(stem, suffix))

    text = html_to_plain(body, document.title or stem)
    return Response(content=text.encode("utf-8"), media_type=media_type,
                    headers=_attach(stem, suffix))


@router.get("/formats/{document_id}")
def available_formats(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """
    Which exports actually work for this document, and why not for the others.

    Offering a .docx button that fails on a scan is worse than not offering it,
    so the screen asks first.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    has_body = bool(document.source_html)
    has_text = bool((document.full_text or "").strip())
    is_pdf = (document.mime_type or "").endswith("pdf")

    return {
        "document_id": document.id,
        "formats": [
            {
                "id": "pdf",
                "label": "PDF",
                "hint": "The document of record, letterhead and all",
                "available": True,
                "reason": "",
                "primary": True,
            },
            {
                "id": "docx",
                "label": "Word (.docx)",
                "hint": "Editable text. The letterhead is not carried over.",
                "available": has_body or has_text,
                "reason": "" if (has_body or has_text)
                          else "No text has been read from this file yet.",
                "primary": False,
            },
            {
                "id": "txt",
                "label": "Plain text (.txt)",
                "hint": "The words only, for another system to consume",
                "available": has_body or has_text,
                "reason": "" if (has_body or has_text)
                          else "No text has been read from this file yet.",
                "primary": False,
            },
        ],
        "is_pdf": is_pdf,
        "version": document.version or "1.0",
    }


# ----------------------------------------------------------------- helpers


def _attach(stem: str, suffix: str) -> dict:
    return {
        "Content-Disposition": f'attachment; filename="{stem}{suffix}"',
        "X-Content-Type-Options": "nosniff",
    }


def _safe_name(title: str) -> str:
    import re

    cleaned = re.sub(r"[^A-Za-z0-9 _-]+", "", title).strip().replace(" ", "_")
    return cleaned[:80] or "document"


def _esc(text: str) -> str:
    return (
        str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ).replace("\n", "<br>")
