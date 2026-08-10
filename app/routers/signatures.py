"""
Where approval signatures sit on the document, and what it looks like signed.

The placement editor needs three things and this router provides exactly those:
the current layout, a picture of the page to place against, and a preview of
the finished article. Saving a layout writes nothing to the document itself -
the signed rendition is produced on demand, and only becomes a stored version
when the document is published.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Document, Signature, User
from ..services import signature_stamp as stamp
from ..services import workflow_service as wf
from ..services.auth_service import require_permission_flexible

router = APIRouter()


class Placement(BaseModel):
    signature_id: str
    page_number: int = Field(ge=1, le=200)
    x_pct: float = Field(ge=0.0, le=1.0)
    y_pct: float = Field(ge=0.0, le=1.0)
    width_pct: float = Field(ge=0.03, le=1.0)


class LayoutPayload(BaseModel):
    placements: list[Placement] = Field(default_factory=list)


class DesignationPayload(BaseModel):
    signature_id: str
    designation: str = Field(default="", max_length=120)


# ------------------------------------------------------------------ helpers


def _document_pdf(db: Session, workflow) -> tuple[Document, bytes]:
    """The document's current bytes, refusing anything that is not a PDF."""
    document = db.query(Document).filter(Document.id == workflow.document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    path = Path(document.file_path) if document.file_path else None
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="The document file is missing from storage")

    if not (document.mime_type or "").endswith("pdf") and path.suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=400,
            detail="Signatures can only be stamped onto a PDF. Export this document as PDF "
                   "first, or write it in the Document Studio.",
        )

    return document, path.read_bytes()


def _load(db: Session, workflow_id: str):
    workflow = wf.load(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Approval process not found")
    return workflow


# ------------------------------------------------------------------- layout


@router.get("/{workflow_id}/layout")
def get_layout(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """
    Every signature, where it currently sits, and the page it sits on.

    Positions come back resolved: a signature nobody has moved reports the
    place the automatic layout would put it, so the editor never has to
    reimplement that rule.
    """
    workflow = _load(db, workflow_id)
    document, pdf = _document_pdf(db, workflow)

    blocks = stamp.blocks_from_workflow(workflow)
    geometry = stamp.page_geometry(pdf)

    if blocks:
        blocks = stamp.resolve(blocks, geometry, pdf)

    return {
        "workflow_id": workflow.id,
        "document_id": document.id,
        "title": document.title or document.original_filename,
        "pages": geometry,
        "page_count": len(geometry),
        # A block placed after the last page means an extra signature sheet.
        "extra_page": any(b.resolved["page"] > len(geometry) for b in blocks),
        "block_height_pct": (
            stamp.BLOCK_H / geometry[-1]["height"] if geometry else 0.1
        ),
        "signatures": [
            {
                "signature_id": b.signature_id,
                "name": b.name,
                "designation": b.designation,
                "step": b.step_name,
                "order": b.order,
                "signed_at": b.signed_at,
                "dataUrl": b.data_url,
                "page_number": b.resolved["page"],
                "x_pct": b.resolved["x"] / b.resolved["page_width"],
                "y_pct": b.resolved["y_top"] / b.resolved["page_height"],
                "width_pct": b.resolved["width"] / b.resolved["page_width"],
                "auto": b.resolved["auto"],
            }
            for b in blocks
        ],
    }


@router.put("/{workflow_id}/layout")
def save_layout(
    workflow_id: str,
    payload: LayoutPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """
    Record where somebody moved the signatures to.

    Only the position is written. The signature itself - the image, the name,
    the designation, the time - is never touched by this: moving a mark on a
    page must not be able to change what it says.
    """
    workflow = _load(db, workflow_id)

    if workflow.status == wf.PUBLISHED:
        raise HTTPException(
            status_code=400,
            detail="This document is already published. Withdraw the publication first if the "
                   "signatures need moving.",
        )

    allowed = {
        step.signature_id for step in workflow.steps if step.signature_id
    }

    moved = 0
    for p in payload.placements:
        if p.signature_id not in allowed:
            continue
        signature = db.query(Signature).filter(Signature.id == p.signature_id).first()
        if not signature:
            continue
        signature.page_number = p.page_number
        signature.x_pct = p.x_pct
        signature.y_pct = p.y_pct
        signature.width_pct = p.width_pct
        signature.placed_by = current_user.id
        signature.placed_at = datetime.utcnow()
        moved += 1

    db.commit()
    return {"message": f"{moved} signature{'' if moved == 1 else 's'} repositioned",
            "moved": moved}


@router.post("/{workflow_id}/layout/reset")
def reset_layout(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """Forget the manual positions and go back to the automatic layout."""
    workflow = _load(db, workflow_id)

    for step in workflow.steps:
        if step.signature:
            step.signature.page_number = None
            step.signature.x_pct = None
            step.signature.y_pct = None
            step.signature.width_pct = None
            step.signature.placed_by = None
            step.signature.placed_at = None

    db.commit()
    return {"message": "Signatures returned to their automatic positions"}


@router.put("/{workflow_id}/designation")
def set_designation(
    workflow_id: str,
    payload: DesignationPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """
    Correct the designation printed under a signature.

    Allowed because a title can be mistyped, and a wrong one on a signed
    document is worse than an editable one. The change is audited, and the
    signature, name and timestamp remain untouchable.
    """
    workflow = _load(db, workflow_id)
    if workflow.status == wf.PUBLISHED:
        raise HTTPException(status_code=400,
                            detail="This document is published. Withdraw it first.")

    allowed = {s.signature_id for s in workflow.steps if s.signature_id}
    if payload.signature_id not in allowed:
        raise HTTPException(status_code=404, detail="That signature is not on this approval")

    signature = db.query(Signature).filter(Signature.id == payload.signature_id).first()
    if not signature:
        raise HTTPException(status_code=404, detail="Signature not found")

    before = signature.designation
    signature.designation = payload.designation.strip()[:120] or None
    db.commit()

    try:
        from ..services.audit_service import log_audit_event
        log_audit_event(
            db=db, user_id=current_user.id, action="signature.designation",
            resource_type="document", resource_id=workflow.document_id,
            details={"signatory": signature.name, "from": before,
                     "to": signature.designation},
        )
    except Exception:
        pass

    return {"message": "Designation updated", "designation": signature.designation}


# ------------------------------------------------------------------ preview


@router.get("/{workflow_id}/preview")
def preview_signed(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """The document as it would be published: signatures stamped on."""
    workflow = _load(db, workflow_id)
    document, pdf = _document_pdf(db, workflow)

    blocks = stamp.blocks_from_workflow(workflow)
    if not blocks:
        # No signatures is a legitimate outcome: every step may have been
        # "approval only". Hand back the document rather than an error.
        return Response(content=pdf, media_type="application/pdf",
                        headers={"Content-Disposition": "inline",
                                 "X-Content-Type-Options": "nosniff",
                                 "X-Signature-Count": "0"})

    try:
        signed = stamp.stamp(pdf, blocks, title=document.title or "")
    except stamp.StampError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return Response(
        content=signed,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
            "X-Signature-Count": str(len(blocks)),
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{workflow_id}/page/{page_number}")
def page_image(
    workflow_id: str,
    page_number: int,
    scale: float = Query(default=1.6, ge=0.5, le=3.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """
    A picture of one page, for the placement editor to work against.

    The unsigned page: the editor draws the signatures itself, so stamping them
    into the backdrop as well would show everything twice.
    """
    workflow = _load(db, workflow_id)
    _document, pdf = _document_pdf(db, workflow)

    geometry = stamp.page_geometry(pdf)
    if page_number > len(geometry):
        # The extra signature sheet has no source page. A blank one of the same
        # size is the honest backdrop for it.
        from PIL import Image
        import io as _io

        last = geometry[-1]
        blank = Image.new("RGB",
                          (int(last["width"] * scale), int(last["height"] * scale)),
                          "white")
        buf = _io.BytesIO()
        blank.save(buf, "PNG")
        data = buf.getvalue()
    else:
        try:
            data = stamp.render_page_png(pdf, page_number, scale)
        except stamp.StampError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    return Response(content=data, media_type="image/png",
                    headers={"Cache-Control": "private, max-age=120"})
