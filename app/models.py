from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column(
        "user_id",
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        Uuid(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")
    mfa: Mapped[UserMfa | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mfa_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("roles.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PasswordRecovery(Base):
    __tablename__ = "password_recoveries"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class UserMfa(Base):
    __tablename__ = "user_mfa"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    encrypted_totp_secret: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="mfa")
    recovery_codes: Mapped[list[MfaRecoveryCode]] = relationship(
        cascade="all, delete-orphan"
    )


class MfaRecoveryCode(Base):
    __tablename__ = "mfa_recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_mfa.user_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginFailure(Base):
    __tablename__ = "login_failures"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(100))
    target_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ManuscriptReferenceCounter(Base):
    __tablename__ = "manuscript_reference_counters"
    __table_args__ = (
        CheckConstraint(
            "value >= 0 AND value <= 999999999999999",
            name="ck_manuscript_reference_counters_value",
        ),
    )

    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'submitted', 'technical_check', "
            "'editorial_screening', 'reviewer_invitation', 'under_review', "
            "'revision_requested', 'resubmitted', 'accepted', 'declined', "
            "'production', 'scheduled', 'published', 'withdrawn')",
            name="ck_submissions_status",
        ),
        CheckConstraint(
            "manuscript_type IS NULL OR manuscript_type IN "
            "('original research', 'review article', 'case study', 'technical paper')",
            name="ck_submissions_manuscript_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reference: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    submitting_author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    manuscript_type: Mapped[str | None] = mapped_column(String(50))
    discipline: Mapped[str | None] = mapped_column(String(30))
    discipline_other: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    abstract: Mapped[str] = mapped_column(Text, default="", nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    authors: Mapped[list[SubmissionAuthor]] = relationship(
        order_by="SubmissionAuthor.position", cascade="all, delete-orphan"
    )
    files: Mapped[list[SubmissionFile]] = relationship(cascade="all, delete-orphan")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SubmissionAuthor(Base):
    __tablename__ = "submission_authors"
    __table_args__ = (UniqueConstraint("submission_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    affiliation: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))


class SubmissionFile(Base):
    __tablename__ = "submission_files"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    storage_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SubmissionWorkflowEvent(Base):
    __tablename__ = "submission_workflow_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    from_status: Mapped[str] = mapped_column(String(30), nullable=False)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EditorAssignment(Base):
    __tablename__ = "editor_assignments"
    __table_args__ = (
        Index("ix_editor_assignments_active", "submission_id", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    editor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    assigned_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    can_make_decisions: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewerProfile(Base):
    __tablename__ = "reviewer_profiles"
    __table_args__ = (Index("ix_reviewer_profiles_email", "email", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    affiliation: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    expertise: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    languages: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    orcid: Mapped[str | None] = mapped_column(String(19))
    profile_url: Mapped[str | None] = mapped_column(String(500))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consent_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReviewAssignment(Base):
    __tablename__ = "review_assignments"
    __table_args__ = (
        UniqueConstraint("submission_id", "reviewer_profile_id", "round_number"),
        CheckConstraint(
            "status IN ('invited', 'accepted', 'declined', 'conflict_reported', "
            "'completed', 'expired', 'cancelled')",
            name="ck_review_assignments_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    reviewer_profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("reviewer_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    manuscript_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("submission_files.id", ondelete="RESTRICT")
    )
    invited_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="invited", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    declined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confidentiality_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    conflict_status: Mapped[str] = mapped_column(
        String(20), default="unanswered", nullable=False
    )
    conflict_details: Mapped[str | None] = mapped_column(Text)
    conflict_resolved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    conflict_resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewReport(Base):
    __tablename__ = "review_reports"
    __table_args__ = (
        UniqueConstraint("review_assignment_id"),
        CheckConstraint(
            "recommendation IN ('accept', 'minor_revision', "
            "'major_revision', 'decline')",
            name="ck_review_reports_recommendation",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    review_assignment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("review_assignments.id", ondelete="CASCADE"),
        nullable=False,
    )
    recommendation: Mapped[str] = mapped_column(String(30), nullable=False)
    comments_to_editor: Mapped[str] = mapped_column(Text, default="", nullable=False)
    comments_to_author: Mapped[str] = mapped_column(Text, default="", nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SubmissionRevision(Base):
    __tablename__ = "submission_revisions"
    __table_args__ = (UniqueConstraint("submission_id", "round_number"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("submission_files.id", ondelete="RESTRICT"),
        nullable=False,
    )
    response_note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EditorialDecision(Base):
    __tablename__ = "editorial_decisions"
    __table_args__ = (
        UniqueConstraint("submission_id", "round_number"),
        CheckConstraint(
            "decision IN ('revision_requested', 'accepted', 'declined')",
            name="ck_editorial_decisions_decision",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    editor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    author_letter: Mapped[str] = mapped_column(Text, nullable=False)
    internal_reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Volume(Base):
    __tablename__ = "volumes"
    __table_args__ = (
        UniqueConstraint("year", "number"),
        CheckConstraint(
            "status IN ('open', 'closed', 'archived')", name="ck_volumes_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Issue(Base):
    __tablename__ = "issues"
    __table_args__ = (
        UniqueConstraint("volume_id", "number"),
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'published', 'closed')",
            name="ck_issues_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    volume_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("volumes.id", ondelete="RESTRICT"),
        nullable=False,
    )
    number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    display_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    cover_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("public_resource_files.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Article(Base):
    __tablename__ = "articles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('production', 'scheduled', 'published', "
            "'withdrawn', 'retracted')",
            name="ck_articles_status",
        ),
        CheckConstraint(
            "doi_verified = false OR doi IS NOT NULL",
            name="ck_articles_verified_doi_present",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("submissions.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    issue_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("issues.id", ondelete="RESTRICT"), index=True
    )
    final_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("submission_files.id", ondelete="SET NULL")
    )
    slug: Mapped[str] = mapped_column(String(220), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    manuscript_type: Mapped[str | None] = mapped_column(String(50))
    discipline: Mapped[str | None] = mapped_column(String(30))
    discipline_other: Mapped[str | None] = mapped_column(String(200))
    references_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    funding: Mapped[str] = mapped_column(Text, default="", nullable=False)
    acknowledgements: Mapped[str] = mapped_column(Text, default="", nullable=False)
    doi: Mapped[str | None] = mapped_column(String(300))
    doi_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    license: Mapped[str | None] = mapped_column(String(300))
    license_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    license_verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    license_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    doi_registration_reference: Mapped[str | None] = mapped_column(String(500))
    doi_verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    doi_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    article_number: Mapped[str | None] = mapped_column(String(50))
    page_range: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(20), default="production", nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ArticleAuthor(Base):
    __tablename__ = "article_authors"
    __table_args__ = (UniqueConstraint("article_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    affiliation: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    orcid: Mapped[str | None] = mapped_column(String(19))


class ArticleHistory(Base):
    __tablename__ = "article_history"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("articles.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ArticleScholarlyAction(Base):
    __tablename__ = "article_scholarly_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('correction', 'expression_of_concern', "
            "'retraction', 'withdrawal')",
            name="ck_article_scholarly_actions_type",
        ),
        CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_article_scholarly_actions_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    article_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("articles.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(30), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CallForPapers(Base):
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    __tablename__ = "calls_for_papers"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'open', 'closed', 'archived')",
            name="ck_calls_for_papers_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(Text, default="", nullable=False)
    manuscript_types: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    related_issue_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("issues.id", ondelete="SET NULL")
    )
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_zone: Mapped[str] = mapped_column(String(100), default="UTC", nullable=False)
    contact: Mapped[str] = mapped_column(String(320), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PublicPage(Base):
    __tablename__ = "public_pages"
    __table_args__ = (
        Index("ix_public_pages_slug", "slug", unique=True),
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_public_pages_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PublicPageHistory(Base):
    __tablename__ = "public_page_history"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("public_pages.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Announcement(Base):
    version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    __tablename__ = "announcements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'published', 'archived')",
            name="ck_announcements_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PublicResourceFile(Base):
    __tablename__ = "public_resource_files"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    storage_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TemplateResource(Base):
    __tablename__ = "template_resources"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'inactive')",
            name="ck_template_resources_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("public_resource_files.id", ondelete="RESTRICT"),
        nullable=False,
    )
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EditorialBoardProfile(Base):
    __tablename__ = "editorial_board_profiles"
    __table_args__ = (
        CheckConstraint(
            "role IN ('editor_in_chief', 'associate_editor', "
            "'managing_editor', 'board_member')",
            name="ck_editorial_board_profiles_role",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    qualifications: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    department: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    institution: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    country: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    specializations: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    biography: Mapped[str] = mapped_column(Text, default="", nullable=False)
    professional_url: Mapped[str | None] = mapped_column(String(500))
    orcid: Mapped[str | None] = mapped_column(String(19))
    professional_email: Mapped[str | None] = mapped_column(String(320))
    photo_file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("public_resource_files.id", ondelete="SET NULL")
    )
    appointment_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    appointment_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    identity_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    qualification_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    affiliation_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    appointment_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    consent_status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )
    consented_public_fields: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    consent_evidence_reference: Mapped[str | None] = mapped_column(String(500))
    public_approved: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    verified_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PresentationResource(Base):
    __tablename__ = "presentation_resources"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'inactive')",
            name="ck_presentation_resources_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    presenter: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    external_url: Mapped[str | None] = mapped_column(String(1000))
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("public_resource_files.id", ondelete="SET NULL")
    )
    related_article_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("articles.id", ondelete="SET NULL")
    )
    related_issue_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("issues.id", ondelete="SET NULL")
    )
    access_status: Mapped[str] = mapped_column(
        String(20), default="public", nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SubmissionChecklist(Base):
    __tablename__ = "submission_checklists"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    declarations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SubmissionReceipt(Base):
    __tablename__ = "submission_receipts"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id"), primary_key=True
    )
    checklist_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submission_checklists.id"), nullable=False
    )
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    declarations: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    manuscript_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class EmailIntake(Base):
    __tablename__ = "email_intakes"
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    message_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    message_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    sender_name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    metadata_fields: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    files: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    warnings: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submission_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("submissions.id"), unique=True
    )


class OutboundMail(Base):
    __tablename__ = "outbound_mail"
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    recipient: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True, nullable=False
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(200))
