"""
The activity log: who did what, when, from where.

Reads the `audit_logs` table that every router writes to. Nothing on this
screen is composed for effect - if an action was not recorded, it does not
appear, and the page says the log is empty rather than inventing a history.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AuditLog, User
from ..services.auth_service import require_permission_flexible

router = APIRouter()

# How each recorded action reads to a person, and how it should be coloured.
# Anything not listed falls back to the raw action name rather than being
# dressed up as something it is not.
ACTIONS = {
    "document.upload":          ("Document uploaded", "capture", ""),
    "document.download":        ("Document downloaded", "download", ""),
    "document.compose":         ("Document written in the Studio", "compose", ""),
    "document.revise":          ("New version saved", "compose", ""),
    "document.publish":         ("Document published", "send", "accent"),
    "document.version.restore": ("Earlier version restored", "history", "warn"),
    "workflow.approve":         ("Approved", "check", "accent"),
    "workflow.reject":          ("Rejected", "x", "danger"),
    "workflow.changes":         ("Sent back for changes", "refresh", "warn"),
    "user_created":             ("Person added", "users", ""),
    "user_updated":             ("Person updated", "users", ""),
    "user_deleted":             ("Person removed", "users", "danger"),
    # These are the exact strings the auth service writes.
    "login_success":            ("Signed in", "user", ""),
    "login_failed":             ("Failed sign-in", "alert", "danger"),
    "logout":                   ("Signed out", "logout", ""),
    "initial_setup":            ("System set up", "settings", "accent"),
    "password_changed":         ("Password changed", "key", ""),
}


def _describe(action: str) -> tuple[str, str, str]:
    return ACTIONS.get(action, (action.replace("_", " ").replace(".", " · "), "info", ""))


@router.get("/")
@router.get("")
def list_events(
    q: Optional[str] = None,
    action: Optional[str] = None,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=200, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """The log, newest first, with the filters the screen offers."""
    since = datetime.utcnow() - timedelta(days=days)

    query = (
        db.query(AuditLog)
        .outerjoin(User, AuditLog.user_id == User.id)
        .filter(AuditLog.created_at >= since)
    )

    if action:
        query = query.filter(AuditLog.action.in_([a.strip() for a in action.split(",")]))

    if q:
        needle = f"%{q.strip().lower()}%"
        query = query.filter(or_(
            func.lower(AuditLog.action).like(needle),
            func.lower(AuditLog.details).like(needle),
            func.lower(AuditLog.resource_type).like(needle),
            func.lower(User.full_name).like(needle),
            func.lower(User.username).like(needle),
        ))

    events = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    # Resolve document ids to titles in one query rather than showing a UUID.
    # An audit row that says "6e22f5b9-21e0-…" tells the reader nothing.
    from ..models import Document

    doc_ids = set()
    parsed = []
    for e in events:
        try:
            detail = json.loads(e.details) if e.details else {}
        except (TypeError, ValueError):
            detail = {}
        parsed.append(detail)
        for key in ("document_id",):
            if detail.get(key):
                doc_ids.add(detail[key])
        if e.resource_type == "document" and e.resource_id:
            doc_ids.add(e.resource_id)

    titles = {}
    if doc_ids:
        for d in db.query(Document).filter(Document.id.in_(doc_ids)).all():
            titles[d.id] = d.title or d.original_filename or d.filename

    out = []
    for e, detail in zip(events, parsed):
        label, icon, tone = _describe(e.action)

        # An entry outlives the account that made it. Saying "System" for a
        # removed person would misattribute what they did.
        if e.user:
            who = e.user.full_name or e.user.username
        elif e.user_id:
            who = "Removed account"
        else:
            who = "System"

        subject = (
            detail.get("title")
            or titles.get(detail.get("document_id") or "")
            or titles.get(e.resource_id or "")
            or detail.get("filename")
            or detail.get("username")
            or ""
        )

        out.append({
            "id": e.id,
            "action": e.action,
            "label": label,
            "icon": icon,
            "tone": tone,
            "user": who,
            "resource_type": e.resource_type,
            "resource_id": e.resource_id,
            "summary": subject,
            "ip_address": e.ip_address,
            "at": e.created_at,
        })

    return {"events": out, "count": len(out), "days": days}


@router.get("/summary")
def summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission_flexible("documents.read")),
):
    """Counts per action and the number of distinct people, over the window."""
    since = datetime.utcnow() - timedelta(days=days)

    rows = (
        db.query(AuditLog.action, func.count(AuditLog.id))
        .filter(AuditLog.created_at >= since)
        .group_by(AuditLog.action)
        .order_by(func.count(AuditLog.id).desc())
        .all()
    )

    # Distinct accounts that acted. Counted from the log rather than from the
    # user table, so somebody who has since been removed still counts: they did
    # act, and the record of it stands.
    accounts = (
        db.query(func.count(func.distinct(AuditLog.user_id)))
        .filter(AuditLog.created_at >= since, AuditLog.user_id.isnot(None))
        .scalar() or 0
    )

    return {
        "days": days,
        "total": sum(n for _, n in rows),
        "people": accounts,
        "actions": [
            {"action": a, "label": _describe(a)[0], "count": n} for a, n in rows
        ],
    }
