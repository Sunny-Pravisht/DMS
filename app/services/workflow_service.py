"""
The approval engine.

Everything that changes a workflow's state goes through this module. Nothing
else moves a step from `current` to `approved`, decides who is next, or marks a
workflow finished. Routers validate input and render output; the rules live
here, once.

The model is deliberately small. A workflow is an ordered chain of steps, and
exactly one of them is `current`. That single invariant answers every question
the product asks:

    where is it now?      the current step
    who is it with?       that step's assignees, or whoever holds its role
    is it done?           there is no current step and none were rejected
    can I act?            I am addressed by the current step, and I am permitted

Two permissions are checked separately and mean different things:

    can_approve   may act on a step at all
    can_sign      may apply a signature to that approval

A step that demands a signature cannot be satisfied by someone who may only
approve. That is the point of having two flags rather than one.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional

from loguru import logger
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..models import (
    ApprovalStep,
    ApprovalWorkflow,
    Document,
    Signature,
    StepDecision,
    User,
    WorkflowEvent,
)

# Statuses, named once so a typo cannot invent a new one.
DRAFT, ACTIVE, APPROVED, REJECTED, CHANGES, CANCELLED, PUBLISHED = (
    "draft", "active", "approved", "rejected", "changes_requested", "cancelled", "published"
)
PENDING, CURRENT = "pending", "current"

# How many of a step's named people must agree.
ANY_OF, ALL_OF = "any", "all"


def outstanding(step: ApprovalStep) -> list[User]:
    """
    Who still has to approve this step before it can close.

    Empty for an "any" step: one decision closes it, so nobody is outstanding
    once somebody has acted. Empty too for a step addressed to a role rather
    than to named people, because there is no list of individuals to wait for.
    """
    if step.approval_mode != ALL_OF or not step.assignees:
        return []
    approved = {d.user_id for d in (step.decisions or []) if d.action == "approved"}
    return [a for a in step.assignees if a.id not in approved]


def has_decided(step: ApprovalStep, user: User) -> bool:
    """Has this person already answered on this step?"""
    return any(d.user_id == user.id for d in (step.decisions or []))

TERMINAL = {APPROVED, REJECTED, CANCELLED, PUBLISHED}

PRIORITIES = ["low", "normal", "high", "urgent"]

# How long a step has, in hours. The labels are what the UI offers.
SLA_CHOICES = {
    "4 hours": 4, "8 hours": 8, "1 day": 24, "2 days": 48,
    "3 days": 72, "5 days": 120, "10 days": 240,
}


class WorkflowError(ValueError):
    """The request is not allowed by the rules of the process."""


# ---------------------------------------------------------------- building


def create_workflow(
    db: Session,
    document: Document,
    author: User,
    *,
    name: str = "Approval",
    template_id: Optional[str] = None,
    priority: str = "normal",
    department: Optional[str] = None,
    due_date: Optional[datetime] = None,
    retention_policy: Optional[str] = None,
    after_approval: Optional[str] = None,
    notes: Optional[str] = None,
    steps: Optional[list[dict]] = None,
    start: bool = True,
) -> ApprovalWorkflow:
    """
    Build a workflow for a document and, by default, start it.

    Replaces any workflow already in flight for the same document: a document
    has one live approval chain, never two competing ones.
    """
    steps = steps or []
    if not steps:
        raise WorkflowError("An approval process needs at least one step.")
    if priority not in PRIORITIES:
        priority = "normal"

    existing = active_for_document(db, document.id)
    if existing:
        cancel_workflow(db, existing, author, reason="Replaced by a new approval process")

    workflow = ApprovalWorkflow(
        document_id=document.id,
        name=(name or "Approval").strip()[:120],
        template_id=template_id,
        status=DRAFT,
        priority=priority,
        created_by=author.id if author else None,
        department=department,
        due_date=due_date,
        retention_policy=retention_policy,
        after_approval=after_approval,
        notes=notes,
    )
    db.add(workflow)
    db.flush()

    for index, raw in enumerate(steps):
        db.add(_build_step(db, workflow, index, raw))

    db.commit()
    db.refresh(workflow)

    if start:
        start_workflow(db, workflow, author)

    return workflow


def _build_step(db: Session, workflow: ApprovalWorkflow, index: int, raw: dict) -> ApprovalStep:
    requires_signature = bool(raw.get("requires_signature") or raw.get("sign"))

    mode = (raw.get("approval_mode") or ANY_OF).strip().lower()
    if mode not in (ANY_OF, ALL_OF):
        mode = ANY_OF

    step = ApprovalStep(
        workflow_id=workflow.id,
        order_index=index,
        name=(raw.get("name") or f"Step {index + 1}").strip()[:120],
        department=(raw.get("department") or raw.get("dept") or "").strip() or None,
        role=(raw.get("role") or raw.get("who") or "").strip() or None,
        requires_signature=requires_signature,
        approval_mode=mode,
        sla_hours=_sla_hours(raw.get("sla")),
        status=PENDING,
    )

    # Named people, when the author chose specific individuals.
    ids = raw.get("assignee_ids") or []
    if ids:
        people = db.query(User).filter(
            User.id.in_(ids),
            User.is_active.is_(True)
        ).all()

        # Preserve the exact order supplied in assignee_ids.
        people_by_id = {person.id: person for person in people}
        people = [people_by_id[user_id] for user_id in ids if user_id in people_by_id]

        _reject_unsignable(people, step)
        step.assignees = people

    # "Everybody" only means something when there is a list of individuals.
    # A step addressed to a role has no roll to call, so it falls back to the
    # only thing it can do rather than waiting for a set that does not exist.
    if step.approval_mode == ALL_OF and len(step.assignees or []) < 2:
        step.approval_mode = ANY_OF

    return step


def _reject_unsignable(people: Iterable[User], step: ApprovalStep) -> None:
    """
    A step that must be signed cannot be handed to someone who cannot sign.

    Caught here rather than at decision time so the author finds out while they
    are still designing the process, not three days later when the document is
    stuck with somebody who is not allowed to move it.
    """
    if not step.requires_signature:
        return
    blocked = [p.full_name or p.username for p in people if not (p.can_sign or p.is_admin)]
    if blocked:
        raise WorkflowError(
            f"Step '{step.name}' requires a signature, but "
            + ", ".join(blocked)
            + (" is" if len(blocked) == 1 else " are")
            + " not permitted to sign. Grant signature authority, choose someone "
              "else, or turn the signature requirement off for this step."
        )


def _sla_hours(value) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value) or None
    return SLA_CHOICES.get(str(value).strip(), None)


# --------------------------------------------------------------- lifecycle


def start_workflow(db: Session, workflow: ApprovalWorkflow, actor: Optional[User]) -> ApprovalWorkflow:
    """Put the first step in play and stamp the deadlines."""
    if workflow.status not in (DRAFT, CHANGES):
        return workflow
    if not workflow.steps:
        raise WorkflowError("This process has no steps to start.")

    now = datetime.utcnow()
    workflow.status = ACTIVE
    workflow.started_at = workflow.started_at or now

    for step in workflow.steps:
        if step.status in (PENDING, CURRENT):
            step.status = PENDING

    first = workflow.steps[0]
    first.status = CURRENT
    first.due_date = _due(now, first.sla_hours)

    if not workflow.due_date:
        total = sum(s.sla_hours or 24 for s in workflow.steps)
        workflow.due_date = _due(now, total)

    _event(db, workflow, None, actor, "started",
           f"Approval started · {len(workflow.steps)} step"
           f"{'' if len(workflow.steps) == 1 else 's'}")
    db.commit()
    db.refresh(workflow)
    return workflow


def _due(base: datetime, hours: Optional[int]) -> Optional[datetime]:
    return base + timedelta(hours=hours) if hours else None


def cancel_workflow(db: Session, workflow: ApprovalWorkflow, actor: Optional[User],
                    reason: str = "") -> ApprovalWorkflow:
    if workflow.status in (APPROVED, PUBLISHED):
        raise WorkflowError("A completed approval cannot be cancelled.")
    workflow.status = CANCELLED
    workflow.completed_at = datetime.utcnow()
    for step in workflow.steps:
        if step.status in (PENDING, CURRENT):
            step.status = "skipped"
    _event(db, workflow, None, actor, "cancelled", reason or "Approval cancelled")
    db.commit()
    return workflow


# ---------------------------------------------------------------- deciding


def can_act(user: User, step: ApprovalStep) -> tuple[bool, str]:
    """
    May this user decide this step, and if not, why not?

    Returns a reason rather than a bare False so the interface can say what is
    wrong instead of just disabling a button.
    """
    if step.status != CURRENT:
        return False, "This step is not the one waiting for a decision."

    # Nobody answers twice, administrators included. On a step that needs
    # everybody, a second approval from the same person would count towards
    # the total and let one signatory close a step meant for three.
    if has_decided(step, user):
        return False, "You have already given your decision on this step."

    if user.is_admin:
        return True, ""

    if not (user.can_approve or user.has_permission("documents.approve")):
        return False, "You do not have permission to approve documents."

    if step.assignees:
        if not any(a.id == user.id for a in step.assignees):
            names = ", ".join(a.full_name or a.username for a in step.assignees)
            return False, f"This step is assigned to {names}."
    elif step.department and user.department and step.department != user.department:
        return False, f"This step is for the {step.department} department."

    if step.requires_signature and not user.can_sign:
        return False, ("This step must be signed, and you are not permitted to "
                       "apply a signature. Ask an administrator for signature authority.")

    return True, ""


def decide(
    db: Session,
    workflow: ApprovalWorkflow,
    step: ApprovalStep,
    user: User,
    action: str,
    *,
    comment: str = "",
    reason: str = "",
    signature: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> ApprovalWorkflow:
    """
    Record one decision and move the chain.

        approve   → step done, next step becomes current, or the whole thing is approved
        reject    → the process ends here
        changes   → back to the author; the chain restarts when they resubmit

    A signature is required exactly when the step says so; supplying one where
    it is not required is accepted and recorded, because a person choosing to
    sign is never a problem.
    """
    if workflow.status not in (ACTIVE,):
        raise WorkflowError("This approval is not active.")

    allowed, why = can_act(user, step)
    if not allowed:
        raise WorkflowError(why)

    action = (action or "").lower()
    if action not in ("approve", "reject", "changes"):
        raise WorkflowError(f"'{action}' is not a decision.")

    if action == "reject" and not reason.strip():
        raise WorkflowError("A rejection must say why.")
    if action == "changes" and not comment.strip():
        raise WorkflowError("Say what needs to change.")

    now = datetime.utcnow()
    step.decided_at = now
    step.decided_by = user.id
    step.comment = comment.strip() or None
    step.reason = reason.strip() or None

    if action == "approve":
        if step.requires_signature:
            if not signature or not signature.get("dataUrl"):
                raise WorkflowError("This step must be signed. Add your signature to approve.")
            if not (user.can_sign or user.is_admin):
                raise WorkflowError("You are not permitted to apply a signature.")

        signature_id = None
        if signature and signature.get("dataUrl"):
            signature_id = _store_signature(db, user, signature, ip_address)
            step.signature_id = signature_id

        # One row per person, so a step needing three approvals keeps three
        # comments and three signatures rather than overwriting the columns.
        _record(db, step, user, "approved", comment, reason, signature_id)

        still_to_go = outstanding(step)
        if still_to_go:
            # The step stays open and stays current. The chain does not move,
            # so the document cannot reach publishing until everybody has
            # signed - which is the whole point of this mode.
            names = ", ".join(_who(p) for p in still_to_go)
            _event(db, workflow, step, user, "approved",
                   f"{_who(user)} approved '{step.name}'"
                   + (" and signed" if signature_id else "")
                   + f" · still waiting on {names}",
                   comment)
            db.commit()
            db.refresh(workflow)
            return workflow

        step.status = APPROVED
        _event(db, workflow, step, user, "approved",
               f"{_who(user)} approved '{step.name}'"
               + (" and signed" if step.signature_id else ""),
               comment)
        _advance(db, workflow, step, user)

    elif action == "reject":
        # A rejection is decisive whatever the mode. Waiting for the other two
        # approvers to agree with a "no" that has already stopped the document
        # would waste their time and change nothing.
        _record(db, step, user, "rejected", comment, reason, None)
        step.status = REJECTED
        workflow.status = REJECTED
        workflow.completed_at = now
        for other in workflow.steps:
            if other.status in (PENDING, CURRENT):
                other.status = "skipped"
        _event(db, workflow, step, user, "rejected",
               f"{_who(user)} rejected at '{step.name}' · {reason}", comment)

    else:  # changes
        # Likewise: the document is going back to its author, so there is
        # nothing left for the remaining approvers to approve.
        _record(db, step, user, "changes", comment, reason, None)
        step.status = CHANGES
        workflow.status = CHANGES
        for other in workflow.steps:
            if other.status in (PENDING, CURRENT):
                other.status = PENDING
        _event(db, workflow, step, user, "changes",
               f"{_who(user)} sent it back from '{step.name}'", comment)

    db.commit()
    db.refresh(workflow)
    return workflow


def _record(db: Session, step: ApprovalStep, user: User, action: str,
            comment: str, reason: str, signature_id: Optional[str]) -> StepDecision:
    """Keep this person's own answer, separate from the step's closing one."""
    decision = StepDecision(
        step_id=step.id,
        user_id=user.id if user else None,
        action=action,
        comment=(comment or "").strip() or None,
        reason=(reason or "").strip() or None,
        signature_id=signature_id,
        decided_at=datetime.utcnow(),
    )
    db.add(decision)
    # Flush so `outstanding()` counts the decision just made; without this the
    # last approver of three would still be reported as outstanding.
    db.flush()
    if step.decisions is not None and decision not in step.decisions:
        step.decisions.append(decision)
    return decision


def _advance(db: Session, workflow: ApprovalWorkflow, step: ApprovalStep, actor: User) -> None:
    """Hand the document to the next step, or finish the workflow."""
    following = [s for s in workflow.steps if s.order_index > step.order_index
                 and s.status == PENDING]

    if following:
        nxt = following[0]
        nxt.status = CURRENT
        nxt.due_date = _due(datetime.utcnow(), nxt.sla_hours)
        return

    workflow.status = APPROVED
    workflow.completed_at = datetime.utcnow()

    # The document itself carries the outcome, so lists and search can show it
    # without joining through the workflow.
    document = db.query(Document).filter(Document.id == workflow.document_id).first()
    if document:
        document.is_approved = True
        document.approved_at = workflow.completed_at
        document.approved_by = actor.id if actor else None

    _event(db, workflow, None, actor, "approved",
           "Fully approved · ready to publish")


def resubmit(db: Session, workflow: ApprovalWorkflow, actor: User,
             note: str = "") -> ApprovalWorkflow:
    """
    The author has addressed the requested changes; run the chain again.

    Every step starts over rather than resuming where it stopped. An approver
    who signed version 1 has not seen version 2, and treating their old
    signature as still valid would be a lie about what they agreed to.
    """
    if workflow.status != CHANGES:
        raise WorkflowError("This approval is not waiting for changes.")

    for step in workflow.steps:
        step.status = PENDING
        step.decided_at = None
        step.decided_by = None
        step.comment = None
        step.reason = None
        step.signature_id = None
        # The individual answers go too. Somebody who approved version 1 has
        # not seen version 2; leaving their row would count them towards the
        # new round and let a step close without them ever looking at it.
        step.decisions.clear()

    workflow.status = DRAFT
    workflow.completed_at = None
    _event(db, workflow, None, actor, "restarted",
           "Author resubmitted · approvals restarted from step 1", note)
    db.commit()
    return start_workflow(db, workflow, actor)


def _store_signature(db: Session, user: User, payload: dict,
                     ip_address: Optional[str]) -> str:
    data_url = payload.get("dataUrl") or ""
    if not data_url.startswith("data:image/"):
        raise WorkflowError("That signature is not a valid image.")
    if len(data_url) > 2_000_000:
        raise WorkflowError("That signature image is too large.")

    # The designation is copied here, not looked up later. Somebody who signs
    # as Head of Finance and is promoted next year must still read as Head of
    # Finance on the document they signed.
    designation = (payload.get("designation") or user.job_title or "").strip()

    signature = Signature(
        user_id=user.id,
        name=(payload.get("name") or user.full_name or user.username)[:120],
        designation=designation[:120] or None,
        method=(payload.get("method") or "draw")[:20],
        data_url=data_url,
        ip_address=ip_address,
    )
    db.add(signature)
    db.flush()
    return signature.id


# ------------------------------------------------------------------ queries


def active_for_document(db: Session, document_id: str) -> Optional[ApprovalWorkflow]:
    """The live workflow for a document, if there is one."""
    return (
        db.query(ApprovalWorkflow)
        .filter(
            ApprovalWorkflow.document_id == document_id,
            ApprovalWorkflow.status.notin_([CANCELLED]),
        )
        .order_by(ApprovalWorkflow.created_at.desc())
        .first()
    )


def load(db: Session, workflow_id: str) -> Optional[ApprovalWorkflow]:
    return (
        db.query(ApprovalWorkflow)
        .options(joinedload(ApprovalWorkflow.steps).joinedload(ApprovalStep.assignees))
        .filter(ApprovalWorkflow.id == workflow_id)
        .first()
    )


def current_step(workflow: ApprovalWorkflow) -> Optional[ApprovalStep]:
    for step in workflow.steps:
        if step.status == CURRENT:
            return step
    return None


def tasks_for(db: Session, user: User) -> list[tuple[ApprovalWorkflow, ApprovalStep]]:
    """
    Every step waiting on this user, soonest deadline first.

    A step reaches someone two ways: they are named on it, or it is addressed to
    their department and nobody was named. Administrators see everything, since
    somebody has to be able to unblock a process when a person is away.
    """
    query = (
        db.query(ApprovalStep)
        .join(ApprovalWorkflow, ApprovalStep.workflow_id == ApprovalWorkflow.id)
        .filter(ApprovalStep.status == CURRENT, ApprovalWorkflow.status == ACTIVE)
    )

    steps = query.all()
    out: list[tuple[ApprovalWorkflow, ApprovalStep]] = []

    for step in steps:
        # A step this person has already answered is not waiting on them, even
        # though it is still open waiting on their colleagues. Leaving it on
        # their list would ask them to approve the same document twice.
        if has_decided(step, user):
            continue
        if user.is_admin:
            out.append((step.workflow, step))
            continue
        if not (user.can_approve or user.has_permission("documents.approve")):
            continue
        if step.assignees:
            if any(a.id == user.id for a in step.assignees):
                out.append((step.workflow, step))
        elif step.department and user.department and step.department == user.department:
            out.append((step.workflow, step))
        elif not step.department and not step.assignees:
            out.append((step.workflow, step))

    out.sort(key=lambda pair: (pair[1].due_date or datetime.max))
    return out


def is_overdue(step: ApprovalStep) -> bool:
    return bool(step.due_date and step.status == CURRENT and step.due_date < datetime.utcnow())


def publish(db: Session, workflow: ApprovalWorkflow, actor: User) -> ApprovalWorkflow:
    """Release an approved document. Only approval earns this."""
    if workflow.status != APPROVED:
        raise WorkflowError("Only a fully approved document can be published.")
    workflow.status = PUBLISHED
    workflow.published_at = datetime.utcnow()
    workflow.published_by = actor.id if actor else None
    _event(db, workflow, None, actor, "published", f"{_who(actor)} published this document")
    db.commit()
    db.refresh(workflow)
    return workflow


def remind(db: Session, workflow: ApprovalWorkflow, actor: User) -> str:
    step = current_step(workflow)
    if not step:
        raise WorkflowError("There is nobody to remind: nothing is waiting.")
    who = (", ".join(a.full_name or a.username for a in step.assignees)
           or step.role or step.department or "the assigned approver")
    _event(db, workflow, step, actor, "reminded", f"Reminder sent to {who}")
    db.commit()
    return who


def escalate_current_step(db: Session, workflow: ApprovalWorkflow, actor: User,
                         reason: str = "Approver unavailable") -> Optional[ApprovalStep]:
    """Escalate a pending step when the primary approver is unavailable."""
    step = current_step(workflow)
    if not step:
        return None

    assignees = sorted(
        list(step.assignees or []),
        key=lambda u: (u.full_name or u.username or "").lower(),
    )
    alternate = None

    if len(assignees) > 1:
        alternate = assignees[1]
    elif assignees:
        primary_id = assignees[0].id
        if step.department:
            candidates = (
                db.query(User)
                .filter(
                    User.is_active.is_(True),
                    User.department == step.department,
                    User.id != primary_id,
                )
                .filter(or_(User.can_approve.is_(True), User.is_admin.is_(True)))
                .order_by(User.full_name, User.username)
                .all()
            )
        else:
            candidates = (
                db.query(User)
                .filter(User.is_active.is_(True), User.id != primary_id)
                .filter(or_(User.can_approve.is_(True), User.is_admin.is_(True)))
                .order_by(User.full_name, User.username)
                .all()
            )
        if candidates:
            alternate = candidates[0]
    else:
        if step.department:
            candidates = (
                db.query(User)
                .filter(User.is_active.is_(True), User.department == step.department)
                .filter(or_(User.can_approve.is_(True), User.is_admin.is_(True)))
                .order_by(User.full_name, User.username)
                .all()
            )
        else:
            candidates = (
                db.query(User)
                .filter(User.is_active.is_(True))
                .filter(or_(User.can_approve.is_(True), User.is_admin.is_(True)))
                .order_by(User.full_name, User.username)
                .all()
            )
        if candidates:
            alternate = candidates[0]

    if not alternate:
        return None

    step.assignees = [alternate]
    step.reason = (reason or "Approver unavailable").strip()[:500] or None
    step.due_date = _due(datetime.utcnow(), step.sla_hours or 24)
    step.updated_at = datetime.utcnow() if hasattr(step, 'updated_at') else None
    _event(db, workflow, step, actor, "escalated",
           f"Escalation: {step.reason} · reassigned to {alternate.full_name or alternate.username}")
    db.commit()
    db.refresh(step)
    return step


# ------------------------------------------------------------------ helpers


def _event(db: Session, workflow: ApprovalWorkflow, step: Optional[ApprovalStep],
           actor: Optional[User], kind: str, summary: str, detail: str = "") -> None:
    db.add(WorkflowEvent(
        workflow_id=workflow.id,
        step_id=step.id if step else None,
        actor_id=actor.id if actor else None,
        kind=kind,
        summary=summary[:400],
        detail=(detail or "").strip() or None,
    ))


def _who(user: Optional[User]) -> str:
    if not user:
        return "The system"
    return user.full_name or user.username


def progress(workflow: ApprovalWorkflow) -> dict:
    """Counts for a progress bar, so every screen reports the same numbers."""
    total = len(workflow.steps)
    done = sum(1 for s in workflow.steps if s.status == APPROVED)
    return {
        "total": total,
        "done": done,
        "percent": int(done / total * 100) if total else 0,
    }
