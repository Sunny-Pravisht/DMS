from sqlalchemy import Column, String, Text, DateTime, Boolean, Float, ForeignKey, Table, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from uuid import uuid4
from passlib.context import CryptContext

from .database import Base

# Association table for many-to-many relationship between documents and tags
document_tags = Table(
    'document_tags',
    Base.metadata,
    Column('document_id', String, ForeignKey('documents.id'), primary_key=True),
    Column('tag_id', String, ForeignKey('tags.id'), primary_key=True)
)

# Association table for document relationships (main doc to sub docs)
document_relations = Table(
    'document_relations',
    Base.metadata,
    Column('parent_document_id', String, ForeignKey('documents.id'), primary_key=True),
    Column('child_document_id', String, ForeignKey('documents.id'), primary_key=True)
)

class Correspondent(Base):
    __tablename__ = "correspondents"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, nullable=True)
    address = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    documents = relationship("Document", back_populates="correspondent")

class DocType(Base):
    __tablename__ = "doctypes"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    documents = relationship("Document", back_populates="doctype")

class Tag(Base):
    __tablename__ = "tags"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name = Column(String, unique=True, nullable=False, index=True)
    color = Column(String, nullable=True)  # For UI representation
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    documents = relationship("Document", secondary=document_tags, back_populates="tags")

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_hash = Column(String, unique=True, nullable=False, index=True)
    file_path = Column(String, nullable=False)  # Path in storage
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String, nullable=False)
    
    # Document metadata
    title = Column(String, nullable=True)
    summary = Column(Text, nullable=True)
    full_text = Column(Text, nullable=True)  # OCR result
    document_date = Column(DateTime, nullable=True)  # Date from document content
    
    # Extended fields as requested
    is_tax_relevant = Column(Boolean, default=False, nullable=False)
    reminder_date = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)  # User notes for the document

    # Authoring. A document is either "uploaded" (a file arrived) or "composed"
    # (written in the Studio). Composed documents keep their editable source so
    # re-opening one is lossless rather than a re-type of the extracted text.
    origin = Column(String, default="uploaded", nullable=True)   # uploaded | composed
    template_id = Column(String, nullable=True)                  # doc_templates id
    source_html = Column(Text, nullable=True)                    # sanitised body
    version = Column(String, default="1.0", nullable=True)
    revision_of = Column(String, nullable=True)                  # documents.id
    created_by = Column(String, nullable=True)                   # users.id
    
    # View tracking
    view_count = Column(Integer, default=0, nullable=False)
    last_viewed = Column(DateTime(timezone=True), nullable=True)
    
    # Foreign keys
    correspondent_id = Column(String, ForeignKey("correspondents.id"), nullable=True)
    doctype_id = Column(String, ForeignKey("doctypes.id"), nullable=True)
    
    # System metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Processing status
    ocr_status = Column(String, default="pending")  # pending, processing, completed, failed
    ai_status = Column(String, default="pending")   # pending, processing, completed, failed
    vector_status = Column(String, default="pending")  # pending, processing, completed, failed
    
    # Approval status
    is_approved = Column(Boolean, default=False, nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    correspondent = relationship("Correspondent", back_populates="documents")
    doctype = relationship("DocType", back_populates="documents")
    tags = relationship("Tag", secondary=document_tags, back_populates="documents")
    approved_by_user = relationship("User", foreign_keys=[approved_by])
    
    # Self-referential relationship for main/sub documents
    children = relationship(
        "Document",
        secondary=document_relations,
        primaryjoin=id == document_relations.c.parent_document_id,
        secondaryjoin=id == document_relations.c.child_document_id,
        backref="parents"
    )

class MediaAsset(Base):
    """
    An image the Studio can place in a document: a brand mark, a stamp, a
    signature, or anything a user uploaded from their own machine.

    Bodies reference assets by id, never by path. That is deliberate: the PDF
    renderer resolves the id against this table, so a body can only ever embed
    a file the server already knows about.
    """
    __tablename__ = "media_assets"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    key = Column(String, unique=True, nullable=True, index=True)  # set for built-ins
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False, default="image")  # logo | stamp | signature | image
    file_path = Column(String, nullable=False)
    mime_type = Column(String, nullable=False, default="image/png")
    file_size = Column(Integer, nullable=True)
    is_builtin = Column(Boolean, default=False, nullable=False)
    is_shared = Column(Boolean, default=True, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", foreign_keys=[owner_id])


class DocumentDraft(Base):
    """
    Work in progress in the Studio. A draft is private to its author until it
    is published, at which point a real Document is created and the draft keeps
    a pointer to it so "edit again" reopens the same body.
    """
    __tablename__ = "document_drafts"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)
    title = Column(String, nullable=False, default="Untitled document")
    template_id = Column(String, nullable=True)
    html = Column(Text, nullable=True)
    meta = Column(Text, nullable=True)          # JSON: doctype, correspondent, dept, tags
    document_id = Column(String, ForeignKey("documents.id"), nullable=True)
    source_document_id = Column(String, nullable=True)   # editing an existing document
    status = Column(String, default="draft", nullable=False)  # draft | published
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner = relationship("User", foreign_keys=[owner_id])


# ---------------------------------------------------------------------------
# Approval workflow
#
# A workflow is one document's journey through a chain of approvers. It is kept
# on the server, not in the browser, because more than one person acts on it:
# the approver who signs step 2 is not the author who built it, and neither can
# see the other's localStorage.
#
# The chain is strictly ordered. Exactly one step is `current` at a time; the
# rest are `pending` ahead of it or decided behind it. That single invariant is
# what makes "where is it now?" answerable without reconstructing history.
# ---------------------------------------------------------------------------

# Which named people a step is addressed to. Empty means "whoever holds the
# role", which is the normal case for a standing process.
step_assignees = Table(
    'step_assignees',
    Base.metadata,
    Column('step_id', String, ForeignKey('approval_steps.id'), primary_key=True),
    Column('user_id', String, ForeignKey('users.id'), primary_key=True),
)


class Signature(Base):
    """
    A signature as applied to one decision.

    Stored per use rather than only on the user, so a signature on a document
    approved last March stays exactly as it was even if the person later draws
    a new one. An audit trail that mutates is not an audit trail.

    The same reasoning applies to the signatory's designation: it is copied here
    at the moment of signing rather than read from the user record later. A
    document signed by somebody who was Head of Finance must keep saying so
    after they move on.
    """
    __tablename__ = "signatures"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    name = Column(String, nullable=False)            # as it should appear
    designation = Column(String, nullable=True)      # job title, frozen at signing
    method = Column(String, nullable=False, default="draw")  # draw | type | upload
    data_url = Column(Text, nullable=False)          # PNG data URL
    signed_at = Column(DateTime(timezone=True), server_default=func.now())
    ip_address = Column(String, nullable=True)

    # Where the signature is stamped on the document, held as a fraction of the
    # page rather than in millimetres. A4 today, Letter tomorrow, a scan at some
    # arbitrary size after that: a proportion stays correct where a coordinate
    # would silently drift. NULL means "wherever the automatic layout puts it".
    page_number = Column(Integer, nullable=True)     # 1-based
    x_pct = Column(Float, nullable=True)             # left edge, 0..1
    y_pct = Column(Float, nullable=True)             # top edge, 0..1
    width_pct = Column(Float, nullable=True)         # block width, 0..1
    placed_by = Column(String, ForeignKey("users.id"), nullable=True)
    placed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    placer = relationship("User", foreign_keys=[placed_by])


class ApprovalWorkflow(Base):
    __tablename__ = "approval_workflows"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    name = Column(String, nullable=False, default="Approval")
    template_id = Column(String, nullable=True)      # the route it was built from

    # draft: still being designed. active: in flight. The rest are terminal
    # except changes_requested, which hands the document back to its author.
    status = Column(String, nullable=False, default="draft", index=True)
    priority = Column(String, nullable=False, default="normal")  # low|normal|high|urgent

    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)

    department = Column(String, nullable=True)
    retention_policy = Column(String, nullable=True)
    after_approval = Column(String, nullable=True)
    notes = Column(Text, nullable=True)

    # Publishing is the end of the line: approved, then released.
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_by = Column(String, ForeignKey("users.id"), nullable=True)

    document = relationship("Document", foreign_keys=[document_id])
    creator = relationship("User", foreign_keys=[created_by])
    publisher = relationship("User", foreign_keys=[published_by])
    steps = relationship(
        "ApprovalStep",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="ApprovalStep.order_index",
    )
    events = relationship(
        "WorkflowEvent",
        back_populates="workflow",
        cascade="all, delete-orphan",
        order_by="WorkflowEvent.created_at",
    )


class ApprovalStep(Base):
    __tablename__ = "approval_steps"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    workflow_id = Column(String, ForeignKey("approval_workflows.id"), nullable=False, index=True)
    order_index = Column(Integer, nullable=False, default=0)
    name = Column(String, nullable=False, default="Review")

    # Who it goes to. Department + role is the standing address; `assignees`
    # narrows it to named people when the author wants specific individuals.
    department = Column(String, nullable=True)
    role = Column(String, nullable=True)

    # The permission this step demands. An approver who may approve but not
    # sign cannot be given a step that requires a signature.
    requires_signature = Column(Boolean, nullable=False, default=False)

    # How many of the named people have to agree.
    #
    #   "any"  one of them decides for the step - the original behaviour
    #   "all"  every named person must approve before the chain moves on
    #
    # Defaulted to "any" so that steps created before this existed, including
    # approvals already in flight, keep behaving exactly as the people on them
    # were told they would. Only a step explicitly built as "all" waits for
    # everybody.
    approval_mode = Column(String, nullable=False, default="any")

    sla_hours = Column(Integer, nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)

    status = Column(String, nullable=False, default="pending")
    # pending | current | approved | rejected | changes_requested | skipped

    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_by = Column(String, ForeignKey("users.id"), nullable=True)
    comment = Column(Text, nullable=True)
    reason = Column(String, nullable=True)
    signature_id = Column(String, ForeignKey("signatures.id"), nullable=True)

    workflow = relationship("ApprovalWorkflow", back_populates="steps")
    decider = relationship("User", foreign_keys=[decided_by])
    signature = relationship("Signature", foreign_keys=[signature_id])
    assignees = relationship("User", secondary=step_assignees)
    decisions = relationship(
        "StepDecision", back_populates="step",
        cascade="all, delete-orphan", order_by="StepDecision.decided_at")


class StepDecision(Base):
    """
    One person's answer on one step.

    The step's own `decided_by` and `signature_id` hold the decision that
    *closed* it, which is all a step needs when one person decides for it. A
    step that requires everybody needs one row per person - three approvers
    means three comments and three signatures, and a single set of columns
    cannot hold them.

    Written for every decision, including on "any" steps, so the trail is the
    same shape everywhere and the tracking screen does not need two ways of
    reading history.
    """
    __tablename__ = "step_decisions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    step_id = Column(String, ForeignKey("approval_steps.id"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)

    action = Column(String, nullable=False)          # approved | rejected | changes
    comment = Column(Text, nullable=True)
    reason = Column(String, nullable=True)
    signature_id = Column(String, ForeignKey("signatures.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True), server_default=func.now())

    step = relationship("ApprovalStep", back_populates="decisions")
    user = relationship("User", foreign_keys=[user_id])
    signature = relationship("Signature", foreign_keys=[signature_id])


class WorkflowEvent(Base):
    """
    The trail. Every decision, reminder, restart and publication, in order.

    Separate from `audit_logs` on purpose: this one is shown to users on the
    tracking screen and is written in their language, while the audit log is
    the security record and is written in the system's.
    """
    __tablename__ = "workflow_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    workflow_id = Column(String, ForeignKey("approval_workflows.id"), nullable=False, index=True)
    step_id = Column(String, ForeignKey("approval_steps.id"), nullable=True)
    actor_id = Column(String, ForeignKey("users.id"), nullable=True)
    kind = Column(String, nullable=False)     # started | approved | rejected | changes | reminded | published | cancelled | restarted
    summary = Column(String, nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    workflow = relationship("ApprovalWorkflow", back_populates="events")
    actor = relationship("User", foreign_keys=[actor_id])


class DocumentVersion(Base):
    """
    One immutable snapshot of a document's file.

    A version is written whenever the bytes change: on capture, on every save
    from the Studio, and when an approval locks a version. Nothing here is ever
    updated in place - restoring an old version writes a *new* version whose
    content happens to match an older one, so the history stays append-only.
    """
    __tablename__ = "document_versions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=False, index=True)
    version = Column(String, nullable=False, default="1.0")
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String, nullable=True)
    file_hash = Column(String, nullable=True)

    source_html = Column(Text, nullable=True)     # editable body, for composed documents
    template_id = Column(String, nullable=True)

    note = Column(String, nullable=True)          # "Initial capture", "Reviewer edits", …
    is_current = Column(Boolean, nullable=False, default=False)
    is_locked = Column(Boolean, nullable=False, default=False)  # approved: cannot be superseded silently

    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    document = relationship("Document", foreign_keys=[document_id])
    author = relationship("User", foreign_keys=[created_by])


class Settings(Base):
    __tablename__ = "settings"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    key = Column(String, unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class ProcessingLog(Base):
    __tablename__ = "processing_logs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    document_id = Column(String, ForeignKey("documents.id"), nullable=True)
    operation = Column(String, nullable=False)  # ocr, ai_extraction, etc.
    status = Column(String, nullable=False)     # success, error, warning
    message = Column(Text, nullable=True)
    execution_time = Column(Integer, nullable=True)  # milliseconds
    created_at = Column(DateTime(timezone=True), server_default=func.now())

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Association table for many-to-many relationship between users and roles
user_roles = Table(
    'user_roles',
    Base.metadata,
    Column('user_id', String, ForeignKey('users.id'), primary_key=True),
    Column('role_id', String, ForeignKey('roles.id'), primary_key=True)
)

class Role(Base):
    __tablename__ = "roles"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    permissions = Column(Text, nullable=True)  # JSON string of permissions
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    users = relationship("User", secondary=user_roles, back_populates="roles")

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    username = Column(String, unique=True, nullable=False, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    full_name = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    must_change_password = Column(Boolean, default=False)

    # Where this person sits, so a step addressed to "AP Manager in Finance"
    # can find them without anyone maintaining a second directory.
    department = Column(String, nullable=True)
    job_title = Column(String, nullable=True)

    # The two approval permissions, kept separate on purpose.
    #
    #   can_approve  may act on an approval step at all
    #   can_sign     may apply a signature to that approval
    #
    # They are not the same authority. A clerk can verify an invoice without
    # being allowed to bind the company; only a signatory does that. Keeping
    # them apart is what lets a step say "approval is enough here" or
    # "this one must be signed" and have the difference actually mean something.
    can_approve = Column(Boolean, default=True, nullable=True)
    can_sign = Column(Boolean, default=False, nullable=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    password_reset_token = Column(String, nullable=True)
    password_reset_expires = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    roles = relationship("Role", secondary=user_roles, back_populates="users")
    
    def set_password(self, password: str):
        """Hash and set password"""
        self.hashed_password = pwd_context.hash(password)
    
    def verify_password(self, password: str) -> bool:
        """Verify password against hash"""
        return pwd_context.verify(password, self.hashed_password)
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has specific permission"""
        if self.is_admin:
            return True
        
        for role in self.roles:
            if role.permissions:
                import json
                try:
                    perms = json.loads(role.permissions)
                    if permission in perms:
                        return True
                except (json.JSONDecodeError, TypeError):
                    continue
        return False

class Session(Base):
    __tablename__ = "sessions"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    session_token = Column(String, unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)  # login, logout, create_document, etc.
    resource_type = Column(String, nullable=True)  # document, user, settings, etc.
    resource_id = Column(String, nullable=True)
    details = Column(Text, nullable=True)  # JSON string with additional details
    ip_address = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    user = relationship("User")
