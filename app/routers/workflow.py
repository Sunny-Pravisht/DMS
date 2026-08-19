"""
Approval workflow API.

The engine in `workflow_service` owns the rules; this layer validates input,
shapes output for the screens, and enforces who may call what. Every response
is built by `_workflow_json` / `_step_json` so Tracking, My Tasks and the
document page can never disagree about a document's state.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    ApprovalStep,
    ApprovalWorkflow,
    Correspondent,
    Document,
    DocType,
    User,
    WorkflowEvent,
)
from ..services import workflow_service as wf
from ..services.auth_service import get_current_user_flexible, require_permission_flexible

router = APIRouter()

# The most workflows one request will return. A caller asking for more
# is given this rather than an error, so a screen can never end up
# silently empty because it asked for too many.
MAX_LIST = 500


# ---------------------------------------------------------------- payloads


class StepPayload(BaseModel):
    name: str = Field(default="Review", max_length=120)
    department: Optional[str] = None
    role: Optional[str] = None
    assignee_ids: list[str] = Field(default_factory=list)
    requires_signature: bool = False
    sla: Optional[str] = None
    # "any" - one of the named people decides for the step
    # "all" - every named person must approve before the chain moves on
    approval_mode: str = "any"


class WorkflowPayload(BaseModel):
    document_id: str
    name: str = Field(default="Approval", max_length=120)
    template_id: Optional[str] = None
    priority: str = "normal"
    department: Optional[str] = None
    due_date: Optional[str] = None
    retention_policy: Optional[str] = None
    after_approval: Optional[str] = None
    notes: Optional[str] = None
    steps: list[StepPayload] = Field(default_factory=list)
    start: bool = True


class DecisionPayload(BaseModel):
    action: str                       # approve | reject | changes
    comment: str = ""
    reason: str = ""
    signature: Optional[dict] = None


class ResubmitPayload(BaseModel):
    note: str = ""


class EscalationPayload(BaseModel):
    reason: str = "Approver unavailable"


# ------------------------------------------------------------ serialisation


def _person(user: Optional[User]) -> Optional[dict]:
    if not user:
        return None
    return {
        "id": user.id,
        "name": user.full_name or user.username,
        "username": user.username,
        "department": user.department,
        "job_title": user.job_title,
        "can_sign": bool(user.can_sign),
        "is_admin": bool(user.is_admin),
    }


def _step_json(step: ApprovalStep, viewer: Optional[User] = None) -> dict:
    allowed, why = (False, "")
    if viewer and step.status == wf.CURRENT:
        allowed, why = wf.can_act(viewer, step)

    return {
        "id": step.id,
        "order": step.order_index + 1,
        "name": step.name,
        "department": step.department,
        "role": step.role,
        "assignees": [_person(a) for a in step.assignees],
        "requires_signature": bool(step.requires_signature),
        "approval_mode": step.approval_mode or "any",
        # Who has answered so far and who is still to come. Empty on an "any"
        # step, where one decision closes it and nobody is left waiting.
        "approved_by": [
            _person(d.user) for d in (step.decisions or []) if d.action == "approved"
        ],
        "outstanding": [_person(p) for p in wf.outstanding(step)],
        "sla_hours": step.sla_hours,
        "due_date": step.due_date,
        "overdue": wf.is_overdue(step),
        "status": step.status,
        "decided_at": step.decided_at,
        "decided_by": _person(step.decider),
        "comment": step.comment,
        "reason": step.reason,
        "signature": (
            {
                "id": step.signature.id,
                "dataUrl": step.signature.data_url,
                "name": step.signature.name,
                "designation": step.signature.designation,
                "method": step.signature.method,
                "signedAt": step.signature.signed_at,
                # Whether somebody has moved it from where the automatic
                # layout would put it.
                "placed": step.signature.x_pct is not None,
            }
            if step.signature else None
        ),
        # What the viewer may do here, resolved server-side so the button and
        # the API can never disagree.
        "can_act": allowed,
        "blocked_reason": why if not allowed else "",
    }


def _document_json(document: Optional[Document]) -> Optional[dict]:
    if not document:
        return None
    return {
        "id": document.id,
        "title": document.title or document.original_filename or document.filename,
        "filename": document.original_filename or document.filename,
        "doctype": document.doctype.name if document.doctype else None,
        "correspondent": document.correspondent.name if document.correspondent else None,
        "file_size": document.file_size,
        "mime_type": document.mime_type,
        "version": document.version or "1.0",
        "origin": document.origin or "uploaded",
        "is_approved": bool(document.is_approved),
        "created_at": document.created_at,
    }


def _workflow_json(workflow: ApprovalWorkflow, viewer: Optional[User] = None,
                   with_events: bool = True) -> dict:
    current = wf.current_step(workflow)
    return {
        "id": workflow.id,
        "document_id": workflow.document_id,
        "document": _document_json(workflow.document),
        "name": workflow.name,
        "template_id": workflow.template_id,
        "status": workflow.status,
        "priority": workflow.priority,
        "department": workflow.department,
        "created_by": _person(workflow.creator),
        "created_at": workflow.created_at,
        "started_at": workflow.started_at,
        "completed_at": workflow.completed_at,
        "due_date": workflow.due_date,
        "published_at": workflow.published_at,
        "published_by": _person(workflow.publisher),
        "retention_policy": workflow.retention_policy,
        "after_approval": workflow.after_approval,
        "notes": workflow.notes,
        "progress": wf.progress(workflow),
        "current_step": _step_json(current, viewer) if current else None,
        "steps": [_step_json(s, viewer) for s in workflow.steps],
        "signatures": [
            {
                "id": s.signature.id,
                "step": s.name,
                "order": s.order_index + 1,
                "by": _person(s.decider),
                "dataUrl": s.signature.data_url,
                "name": s.signature.name,
                "designation": s.signature.designation,
                "signedAt": s.signature.signed_at,
                "placed": s.signature.x_pct is not None,
            }
            for s in workflow.steps if s.signature
        ],
        "events": ([
            {
                "id": e.id,
                "kind": e.kind,
                "summary": e.summary,
                "detail": e.detail,
                "actor": _person(e.actor),
                "at": e.created_at,
            }
            for e in workflow.events
        ] if with_events else []),
    }


# -------------------------------------------------------------------- CRUD


@router.post("")
@router.post("/")
def create(
    payload: WorkflowPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """Build an approval process for a document and start it."""
    document = db.query(Document).filter(Document.id == payload.document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    due = None
    if payload.due_date:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
            try:
                due = datetime.strptime(payload.due_date[:len(fmt) + 2].rstrip("Z"), fmt)
                break
            except ValueError:
                continue

    try:
        workflow = wf.create_workflow(
            db, document, current_user,
            name=payload.name,
            template_id=payload.template_id,
            priority=payload.priority,
            department=payload.department,
            due_date=due,
            retention_policy=payload.retention_policy,
            after_approval=payload.after_approval,
            notes=payload.notes,
            steps=[s.model_dump() for s in payload.steps],
            start=payload.start,
        )
    except wf.WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return _workflow_json(wf.load(db, workflow.id), current_user)


@router.get("")
@router.get("/")
def list_workflows(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    q: Optional[str] = None,
    mine: bool = False,
    # Clamped, not rejected. This used to be `le=200`, which answered 422 to
    # anything larger - and the Approval Routes screen asks for 500. Callers
    # use api.safe(), so the 422 became an empty list and the screen showed no
    # usage at all, silently. A request for more than the ceiling now gets the
    # ceiling, which is what the caller wanted anyway.
    limit: int = Query(default=50, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """
    Everything in flight, with the filters the Tracking screen offers.

    `q` searches the document title, filename, correspondent, document type and
    the workflow's own name, because a person looking for "the Maruti invoice"
    does not know or care which of those fields held the word.
    """
    limit = min(limit, MAX_LIST)
    query = (
        db.query(ApprovalWorkflow)
        .join(Document, ApprovalWorkflow.document_id == Document.id)
        .outerjoin(Correspondent, Document.correspondent_id == Correspondent.id)
        .outerjoin(DocType, Document.doctype_id == DocType.id)
    )

    if status:
        query = query.filter(ApprovalWorkflow.status.in_([s.strip() for s in status.split(",")]))
    if priority:
        query = query.filter(ApprovalWorkflow.priority == priority)
    if mine:
        query = query.filter(ApprovalWorkflow.created_by == current_user.id)

    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.filter(or_(
            func.lower(Document.title).like(needle),
            func.lower(Document.original_filename).like(needle),
            func.lower(Correspondent.name).like(needle),
            func.lower(DocType.name).like(needle),
            func.lower(ApprovalWorkflow.name).like(needle),
        ))

    workflows = query.order_by(ApprovalWorkflow.created_at.desc()).limit(limit).all()
    return {
        "workflows": [_workflow_json(w, current_user, with_events=False) for w in workflows],
        "count": len(workflows),
    }


@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """
    The numbers on the Home screen. Every one is counted, never estimated.
    """
    mine = wf.tasks_for(db, current_user)
    overdue_mine = sum(1 for _, step in mine if wf.is_overdue(step))
    due_today = sum(
        1 for _, step in mine
        if step.due_date and step.due_date.date() == datetime.utcnow().date()
    )

    def count(**filters):
        query = db.query(func.count(ApprovalWorkflow.id))
        for key, value in filters.items():
            query = query.filter(getattr(ApprovalWorkflow, key) == value)
        return query.scalar() or 0

    all_overdue = (
        db.query(func.count(ApprovalStep.id))
        .join(ApprovalWorkflow, ApprovalStep.workflow_id == ApprovalWorkflow.id)
        .filter(
            ApprovalStep.status == wf.CURRENT,
            ApprovalWorkflow.status == wf.ACTIVE,
            ApprovalStep.due_date < datetime.utcnow(),
        )
        .scalar() or 0
    )

    documents = db.query(func.count(Document.id)).scalar() or 0
    unconfirmed = (
        db.query(func.count(Document.id))
        .outerjoin(ApprovalWorkflow, ApprovalWorkflow.document_id == Document.id)
        .filter(ApprovalWorkflow.id.is_(None))
        .scalar() or 0
    )

    return {
        "my_tasks": len(mine),
        "my_tasks_overdue": overdue_mine,
        "my_tasks_due_today": due_today,
        "in_progress": count(status=wf.ACTIVE),
        "awaiting_changes": count(status=wf.CHANGES),
        "approved": count(status=wf.APPROVED),
        "published": count(status=wf.PUBLISHED),
        "rejected": count(status=wf.REJECTED),
        "overdue": all_overdue,
        "documents": documents,
        "not_in_a_process": unconfirmed,
        "ready_to_publish": count(status=wf.APPROVED),
    }


@router.get("/tasks/mine")
def my_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Every step waiting on the signed-in user, soonest deadline first."""
    pairs = wf.tasks_for(db, current_user)
    return {
        "tasks": [
            {
                "workflow": _workflow_json(w, current_user, with_events=False),
                "step": _step_json(s, current_user),
            }
            for w, s in pairs
        ],
        "count": len(pairs),
        "can_approve": bool(current_user.can_approve or current_user.is_admin),
        "can_sign": bool(current_user.can_sign or current_user.is_admin),
    }


@router.get("/by-document/{document_id}")
def by_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    workflow = wf.active_for_document(db, document_id)
    if not workflow:
        return {"workflow": None}
    return {"workflow": _workflow_json(wf.load(db, workflow.id), current_user)}


@router.get("/{workflow_id}")
def get_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    workflow = wf.load(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Approval process not found")
    return _workflow_json(workflow, current_user)


# ---------------------------------------------------------------- decisions


@router.post("/{workflow_id}/steps/{step_id}/decide")
def decide(
    workflow_id: str,
    step_id: str,
    payload: DecisionPayload,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_flexible),
):
    """Approve, reject, or send back. The engine decides whether it is allowed."""
    workflow = wf.load(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Approval process not found")

    step = next((s for s in workflow.steps if s.id == step_id), None)
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    try:
        workflow = wf.decide(
            db, workflow, step, current_user, payload.action,
            comment=payload.comment,
            reason=payload.reason,
            signature=payload.signature,
            ip_address=request.client.host if request.client else None,
        )
    except wf.WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _audit(db, current_user, workflow, f"workflow.{payload.action}")
    return _workflow_json(wf.load(db, workflow.id), current_user)


@router.post("/{workflow_id}/resubmit")
def resubmit(
    workflow_id: str,
    payload: ResubmitPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """The author has made the requested changes; run the approvals again."""
    workflow = wf.load(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Approval process not found")
    try:
        workflow = wf.resubmit(db, workflow, current_user, payload.note)
    except wf.WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _workflow_json(wf.load(db, workflow.id), current_user)


@router.post("/{workflow_id}/remind")
def remind(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    workflow = wf.load(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Approval process not found")
    try:
        who = wf.remind(db, workflow, current_user)
    except wf.WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": f"Reminder sent to {who}", "notified": who}


@router.post("/{workflow_id}/escalate")
def escalate(
    workflow_id: str,
    payload: EscalationPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    """Reassign a current approval step when the default approver is unavailable."""
    workflow = wf.load(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Approval process not found")

    step = wf.current_step(workflow)
    if not step:
        raise HTTPException(status_code=400, detail="There is no step waiting for escalation.")

    try:
        escalated = wf.escalate_current_step(db, workflow, current_user, reason=payload.reason)
    except wf.WorkflowError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not escalated:
        raise HTTPException(status_code=400, detail="No alternate approver was available for escalation.")
    return {
        "message": "Approval step escalated",
        "step": _step_json(escalated, current_user),
        "workflow": _workflow_json(wf.load(db, workflow.id), current_user),
    }


@router.post("/{workflow_id}/cancel")
def cancel(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.update")),
):
    workflow = wf.load(db, workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Approval process not found")
    try:
        wf.cancel_workflow(db, workflow, current_user, "Cancelled by the author")
    except wf.WorkflowError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"message": "Approval cancelled"}


# ------------------------------------------------------------------ people


@router.get("/people/approvers")
def approvers(
    department: Optional[str] = None,
    requires_signature: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """
    Who can be put on a step.

    Filtered by what the step actually demands: ask for a signing step and only
    people permitted to sign come back, so an unworkable process cannot be
    designed in the first place.
    """
    query = db.query(User).filter(User.is_active.is_(True))
    if department:
        query = query.filter(or_(User.department == department, User.is_admin.is_(True)))
    if requires_signature:
        query = query.filter(or_(User.can_sign.is_(True), User.is_admin.is_(True)))
    else:
        query = query.filter(or_(User.can_approve.is_(True), User.is_admin.is_(True)))

    people = query.order_by(User.full_name, User.username).all()
    return {"people": [_person(p) for p in people]}


def _audit(db: Session, user: User, workflow: ApprovalWorkflow, action: str) -> None:
    try:
        from ..services.audit_service import log_audit_event

        log_audit_event(
            db=db, user_id=user.id, action=action,
            resource_type="workflow", resource_id=workflow.id,
            details={"document_id": workflow.document_id, "status": workflow.status},
        )
    except Exception:  # auditing must never block a decision
        pass
