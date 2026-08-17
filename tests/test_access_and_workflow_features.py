from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import ApprovalStep, ApprovalWorkflow, Document, DocumentFolder, DocumentVersion, User
from app.services import workflow_service as wf
from app.services.folder_service import create_folder, list_user_folders
from app.services.role_service import apply_role
from app.services.version_service import capture, checkout_version, compare_versions


def _make_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return engine


def _make_user(db, username, **kwargs):
    user = User(
        username=username,
        email=f"{username}@example.com",
        full_name=username.title(),
        is_active=True,
        is_admin=kwargs.pop("is_admin", False),
        department=kwargs.pop("department", None),
        job_title=kwargs.pop("job_title", None),
        can_approve=kwargs.pop("can_approve", False),
        can_sign=kwargs.pop("can_sign", False),
        **kwargs,
    )
    user.set_password("secret")
    db.add(user)
    db.commit()
    db.refresh(user)
    if user.can_approve or user.can_sign or user.is_admin:
        apply_role(db, user)
    return user


def test_role_assignment_and_document_access():
    engine = _make_engine()
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        user = _make_user(db, "alice", can_approve=True)
        admin = _make_user(db, "admin", is_admin=True)

        doc = Document(
            filename="invoice.pdf",
            original_filename="invoice.pdf",
            file_hash="abc123",
            file_path="/tmp/invoice.pdf",
            file_size=1024,
            mime_type="application/pdf",
            title="Invoice",
            created_by=user.id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        assert user.has_permission("documents.read")
        assert user.has_permission("documents.approve")
        assert doc.file_path == "/tmp/invoice.pdf"
        assert admin.has_permission("documents.read")
    finally:
        db.close()


def test_version_compare_and_checkout_restore_latest():
    engine = _make_engine()
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        user = _make_user(db, "editor", can_approve=True)
        base = Path("/tmp")
        base.mkdir(exist_ok=True)
        source = base / "doc_compare.txt"
        source.write_text("first version\nhello\n", encoding="utf-8")

        doc = Document(
            filename="doc_compare.txt",
            original_filename="doc_compare.txt",
            file_hash="hash-one",
            file_path=str(source),
            file_size=source.stat().st_size,
            mime_type="text/plain",
            title="Versioned doc",
            created_by=user.id,
            version="1.0",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        v1 = capture(db, doc, author=user, note="initial", version="1.0")
        source.write_text("second version\nhello\nworld\n", encoding="utf-8")
        doc.file_path = str(source)
        doc.file_size = source.stat().st_size
        doc.version = "1.1"
        doc.file_hash = "hash-two"
        db.commit()

        v2 = capture(db, doc, author=user, note="updated", version="1.1")

        comparison = compare_versions(db, doc.id, v1.id, v2.id)
        assert comparison["different"] is True
        assert comparison["left_version"] == "1.0"
        assert comparison["right_version"] == "1.1"

        restored = checkout_version(db, doc, v1.id, actor=user)
        assert restored.version == "1.0"
        assert doc.version.startswith("1.")
    finally:
        db.close()


def test_escalation_moves_pending_approval_to_alternate_assignee():
    engine = _make_engine()
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        approver_a = _make_user(db, "approver_a", department="Finance", can_approve=True)
        approver_b = _make_user(db, "approver_b", department="Finance", can_approve=True)
        admin = _make_user(db, "ops", is_admin=True)

        doc = Document(
            filename="approval.pdf",
            original_filename="approval.pdf",
            file_hash="approval-hash",
            file_path="/tmp/approval.pdf",
            file_size=4,
            mime_type="application/pdf",
            title="Approval doc",
            created_by=admin.id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        workflow = wf.create_workflow(
            db,
            doc,
            admin,
            steps=[{
                "name": "Finance review",
                "assignee_ids": [approver_a.id, approver_b.id],
                "approval_mode": "any",
                "sla": "4 hours",
            }],
            start=True,
        )
        step = wf.current_step(workflow)
        assert step is not None
        step.due_date = datetime.utcnow() - timedelta(hours=1)
        db.commit()

        escalated = wf.escalate_current_step(db, workflow, admin, reason="Approver unavailable")
        assert escalated is not None
        assert any(a.id == approver_b.id for a in escalated.assignees)
        assert escalated.due_date is not None
        assert escalated.reason or "Approver unavailable" in "".join([
            e.summary for e in workflow.events
        ])
    finally:
        db.close()


def test_user_folder_creation_and_listing():
    engine = _make_engine()
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        user = _make_user(db, "folder_owner", can_approve=True)

        folder = create_folder(db, user.id, "Invoices")
        assert folder.name == "Invoices"

        stored = list_user_folders(db, user.id)
        assert any(item["id"] == folder.id for item in stored)

        doc = Document(
            filename="foldered.pdf",
            original_filename="foldered.pdf",
            file_hash="folder-doc-hash",
            file_path="/tmp/foldered.pdf",
            file_size=10,
            mime_type="application/pdf",
            title="In folder",
            created_by=user.id,
            folder_id=folder.id,
        )
        db.add(doc)
        db.commit()

        folder_docs = folder.documents
        assert any(item.id == doc.id for item in folder_docs)
    finally:
        db.close()
