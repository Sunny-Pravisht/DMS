"""
Standard roles, and keeping a person's role in step with what they may do.

Two systems of permission meet here and they answer different questions:

    a Role         what parts of the product this person can reach at all
                   (read documents, upload, edit, manage settings)

    can_approve /  whether this person may act on an approval step, and
    can_sign       whether they may put a signature on it

Before this existed, creating a member through the interface produced somebody
with the second and none of the first: they could be assigned an approval and
then get a 403 the moment they tried to open the document. Every user now
carries a role matching their authority, assigned when they are created and
re-checked whenever their permissions change.
"""
from __future__ import annotations

import json

from loguru import logger
from sqlalchemy.orm import Session

from ..models import Role, User

READ = [
    "documents.read", "correspondents.read", "doctypes.read", "tags.read",
    "settings.read", "search.read",
]

CONTRIBUTE = READ + [
    "documents.create", "documents.update", "documents.delete",
    "correspondents.create", "correspondents.update",
    "doctypes.create", "tags.create", "tags.update",
]

# name -> (description, permissions)
STANDARD_ROLES: dict[str, tuple[str, list[str]]] = {
    "reader": (
        "Can find and read documents, but not change or approve them.",
        READ,
    ),
    "contributor": (
        "Can add documents and correct their details. Cannot approve.",
        CONTRIBUTE,
    ),
    "approver": (
        "Can add documents and act on approval steps addressed to them.",
        CONTRIBUTE + ["documents.approve"],
    ),
    "signatory": (
        "An approver who may also apply a signature, binding the company.",
        CONTRIBUTE + ["documents.approve", "documents.sign"],
    ),
}


def ensure_standard_roles(db: Session) -> int:
    """Create any missing standard role. Idempotent; safe on every startup."""
    created = 0
    for name, (description, permissions) in STANDARD_ROLES.items():
        role = db.query(Role).filter(Role.name == name).first()
        if role:
            # Keep an existing role's permissions current with this file, so a
            # permission added here reaches people who already hold the role.
            wanted = json.dumps(permissions)
            if role.permissions != wanted:
                role.permissions = wanted
                db.commit()
            continue
        db.add(Role(name=name, description=description,
                    permissions=json.dumps(permissions)))
        created += 1

    if created:
        db.commit()
        logger.info(f"Created {created} standard role(s)")
    return created


def role_for(user: User) -> str:
    """Which standard role matches this person's approval authority."""
    if user.can_sign:
        return "signatory"
    if user.can_approve:
        return "approver"
    return "reader"


def apply_role(db: Session, user: User) -> str:
    """
    Give a user the standard role their permissions imply.

    Any other role they hold is left alone: an administrator may have granted a
    bespoke one deliberately, and this should not quietly undo that. Only the
    standard roles are swapped between.
    """
    ensure_standard_roles(db)

    wanted = role_for(user)
    target = db.query(Role).filter(Role.name == wanted).first()
    if not target:
        return wanted

    user.roles = [r for r in user.roles if r.name not in STANDARD_ROLES]
    user.roles.append(target)
    db.commit()
    return wanted


def backfill(db: Session) -> int:
    """
    Give a role to any active user who has none.

    Runs once at startup for databases created before roles were assigned on
    user creation, so nobody is left able to sign in but unable to read.
    """
    ensure_standard_roles(db)

    fixed = 0
    for user in db.query(User).filter(User.is_active.is_(True)).all():
        if user.is_admin or user.roles:
            continue
        apply_role(db, user)
        fixed += 1

    if fixed:
        logger.info(f"Assigned a standard role to {fixed} user(s) who had none")
    return fixed
