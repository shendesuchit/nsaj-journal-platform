from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, load_only

from app.api.auth import (
    get_authenticated_user,
    get_author_user,
    require_csrf,
)
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    AuditEvent,
    EditorAssignment,
    EditorialDecision,
    Invitation,
    ReviewAssignment,
    ReviewerProfile,
    ReviewReport,
    Role,
    Submission,
    SubmissionFile,
    SubmissionRevision,
    SubmissionWorkflowEvent,
    User,
)
from app.services.accountability import operator_id, audit_details
from app.services.mail_delivery import queue_message, require_delivery
from app.services.private_files import safe_private_path, store_upload
from app.services.security import hash_secret, new_one_time_secret, normalize_email
from app.services.workflow_progress import (
    current_review_round,
    load_editorial_summaries,
    public_progress,
)

router = APIRouter(tags=["editorial workflow"])
DB = Annotated[Session, Depends(get_db)]
EDITOR_ROLES = {"editor_in_chief", "managing_editor", "associate_editor"}
PRIVILEGED_CONFIDENTIAL_ROLE = "site_admin"
TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"technical_check", "withdrawn"},
    "technical_check": {"editorial_screening", "revision_requested", "declined"},
    "editorial_screening": {
        "reviewer_invitation",
        "revision_requested",
        "accepted",
        "declined",
    },
    "reviewer_invitation": {"under_review", "editorial_screening", "declined"},
    "under_review": {
        "editorial_screening",
        "revision_requested",
        "accepted",
        "declined",
    },
    "revision_requested": {"resubmitted", "withdrawn"},
    "resubmitted": {"technical_check", "editorial_screening"},
    "accepted": {"production", "withdrawn"},
    "production": {"scheduled"},
    "scheduled": {"published"},
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssignEditorInput(StrictModel):
    editor_id: uuid.UUID
    can_make_decisions: bool = False


class TransitionInput(StrictModel):
    to_status: str
    reason: str = Field(min_length=3, max_length=4000)


class ReviewerInviteInput(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    affiliation: str = Field(default="", max_length=500)
    expertise: list[str] = Field(default_factory=list, max_length=30)
    languages: list[str] = Field(default_factory=list, max_length=20)
    due_at: datetime
    round_number: int = Field(default=1, ge=1, le=20)

    @field_validator("due_at")
    @classmethod
    def due_date_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("due_at must include a timezone; UTC is recommended")
        return value.astimezone(UTC)

    @field_validator("email")
    @classmethod
    def email_must_be_valid(cls, value: str) -> str:
        normalized = normalize_email(value)
        if (
            "@" not in normalized
            or normalized.startswith("@")
            or normalized.endswith("@")
        ):
            raise ValueError("A valid email address is required")
        if any(character.isspace() for character in normalized):
            raise ValueError("A valid email address is required")
        return normalized


class ReviewResponseInput(StrictModel):
    accept: bool
    confidentiality_accepted: bool = False
    has_conflict: bool = False
    conflict_details: str = Field(default="", max_length=4000)


class ReviewReportInput(StrictModel):
    recommendation: Literal["accept", "minor_revision", "major_revision", "decline"]
    comments_to_editor: str = Field(default="", max_length=30_000)
    comments_to_author: str = Field(default="", max_length=30_000)


class DecisionInput(StrictModel):
    close_open_reviews: bool = False
    review_closure_reason: str = Field(default="", max_length=4000)
    decision: Literal["revision_requested", "accepted", "declined"]
    author_letter: str = Field(min_length=1, max_length=30_000)
    internal_reason: str = Field(default="", max_length=4000)
    round_number: int = Field(default=1, ge=1, le=20)


def _roles(user: User) -> set[str]:
    return {role.name for role in user.roles}


def _require_editor(user: User) -> User:
    roles = _roles(user)
    if PRIVILEGED_CONFIDENTIAL_ROLE in roles or not (roles & EDITOR_ROLES):
        raise HTTPException(
            status_code=403, detail="An assigned editor role is required."
        )
    return user


def _require_reviewer(user: User) -> User:
    roles = _roles(user)
    if PRIVILEGED_CONFIDENTIAL_ROLE in roles or "reviewer" not in roles:
        raise HTTPException(status_code=403, detail="A Reviewer role is required.")
    return user


def _audit(
    db: Session,
    event: str,
    actor_id: uuid.UUID | None,
    target_type: str,
    target_id: uuid.UUID | str,
    details: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_id=operator_id(db, actor_id),
            event_type=event,
            target_type=target_type,
            target_id=str(target_id),
            details=audit_details(db, details),
        )
    )


def _active_editor_assignment(
    db: Session, submission_id: uuid.UUID, editor_id: uuid.UUID
) -> EditorAssignment:
    assignment = db.scalar(
        select(EditorAssignment).where(
            EditorAssignment.submission_id == submission_id,
            EditorAssignment.editor_id == editor_id,
            EditorAssignment.is_active.is_(True),
        )
    )
    if assignment is None:
        raise HTTPException(
            status_code=404, detail="Assigned editorial case not found."
        )
    return assignment


def _editorial_submission(db: Session, submission_id: uuid.UUID) -> Submission:
    submission = db.scalar(select(Submission).where(Submission.id == submission_id).with_for_update())
    if submission is None or submission.status == "draft":
        raise HTTPException(status_code=404, detail="Editorial case not found.")
    return submission


def _write_transition(
    db: Session,
    submission: Submission,
    actor_id: uuid.UUID,
    to_status: str,
    reason: str,
) -> None:
    previous = submission.status
    if to_status not in TRANSITIONS.get(previous, set()):
        raise HTTPException(
            status_code=409,
            detail=f"The transition from {previous} to {to_status} is not allowed.",
        )
    submission.status = to_status
    db.add(
        SubmissionWorkflowEvent(
            submission_id=submission.id,
            actor_id=operator_id(db, actor_id),
            from_status=previous,
            to_status=to_status,
            reason=reason,
        )
    )
    _audit(
        db,
        "submission.status_changed",
        actor_id,
        "submission",
        submission.id,
        {"from": previous, "to": to_status, "reason": reason},
    )


def manual_transitions(submission):
    return {"submitted": ["technical_check", "withdrawn"], "technical_check": ["editorial_screening"],
            "resubmitted": ["technical_check", "editorial_screening"]}.get(submission.status, [])


def _profile_for_user(db: Session, user: User) -> ReviewerProfile:
    profile = db.scalar(
        select(ReviewerProfile).where(ReviewerProfile.user_id == user.id)
    )
    if profile is None or not profile.is_active:
        raise HTTPException(status_code=403, detail="Reviewer profile is not active.")
    return profile


def _review_assignment(
    db: Session, assignment_id: uuid.UUID, reviewer: User
) -> ReviewAssignment:
    profile = _profile_for_user(db, reviewer)
    assignment = db.scalar(
        select(ReviewAssignment).where(
            ReviewAssignment.id == assignment_id,
            ReviewAssignment.reviewer_profile_id == profile.id,
            ReviewAssignment.reviewer_user_id == reviewer.id,
        )
    )
    if assignment is None:
        raise HTTPException(status_code=404, detail="Review assignment not found.")
    return assignment


def _require_review_access(assignment: ReviewAssignment) -> None:
    if assignment.status != "accepted":
        raise HTTPException(
            status_code=403, detail="This review assignment is not active."
        )
    if assignment.conflict_status != "clear":
        raise HTTPException(status_code=403, detail="Conflict resolution is pending.")
    if assignment.confidentiality_accepted_at is None:
        raise HTTPException(
            status_code=403, detail="Confidentiality acknowledgement is required."
        )


def _expire_invitation(db: Session, assignment: ReviewAssignment) -> bool:
    if assignment.status != "invited" or assignment.due_at is None:
        return False
    due_at = assignment.due_at
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=UTC)
    if due_at > datetime.now(UTC):
        return False
    assignment.status = "expired"
    _audit(db, "review.invitation_expired", None, "review_assignment", assignment.id)
    return True


@router.get("/api/v1/editorial/queue")
def editorial_queue(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    editor = _require_editor(actor)
    assignments = db.scalars(
        select(EditorAssignment).where(
            EditorAssignment.editor_id == editor.id,
            EditorAssignment.is_active.is_(True),
        )
    ).all()
    items = []
    for assignment in assignments:
        submission = db.get(Submission, assignment.submission_id)
        if submission is not None:
            items.append(
                {
                    "id": str(submission.id),
                    "reference": submission.reference,
                    "title": submission.title,
                    "status": submission.status,
                    "assigned_at": assignment.assigned_at.isoformat(),
                    "can_make_decisions": assignment.can_make_decisions,
                }
            )
    return {"items": items}


@router.get("/api/v1/editorial/unassigned")
def unassigned_submissions(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    if "site_admin" in _roles(actor) or "editor_in_chief" not in _roles(actor):
        raise HTTPException(
            status_code=403,
            detail="Only the Editor-in-Chief may view unassigned cases.",
        )
    active_assignments = db.scalars(
        select(EditorAssignment.submission_id).where(
            EditorAssignment.is_active.is_(True)
        )
    ).all()
    statement = select(Submission).where(Submission.status != "draft")
    if active_assignments:
        statement = statement.where(Submission.id.not_in(active_assignments))
    submissions = db.scalars(statement.order_by(Submission.created_at.asc())).all()
    return {
        "items": [
            {
                "id": str(submission.id),
                "reference": submission.reference,
                "title": submission.title,
                "status": submission.status,
            }
            for submission in submissions
        ]
    }


@router.get("/api/v1/editorial/worklist")
def editorial_worklist(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    """Offer team metadata to the Chief without expanding case-detail access."""
    editor = _require_editor(actor)
    statement = (
        select(Submission)
        .options(
            load_only(
                Submission.id,
                Submission.reference,
                Submission.title,
                Submission.status,
                Submission.updated_at,
            )
        )
        .where(Submission.status != "draft")
    )
    if "editor_in_chief" not in _roles(editor):
        assigned_cases = select(EditorAssignment.submission_id).where(
            EditorAssignment.editor_id == editor.id,
            EditorAssignment.is_active.is_(True),
        )
        statement = statement.where(Submission.id.in_(assigned_cases))
    submissions = db.scalars(
        statement.order_by(Submission.updated_at.desc(), Submission.id)
    ).all()
    summaries = load_editorial_summaries(db, submissions)
    return {
        "items": [
            {
                "id": str(submission.id),
                "reference": submission.reference,
                "title": submission.title,
                "status": submission.status,
                "assigned_editors": summaries[submission.id].assigned_editors,
                "is_assigned_to_me": editor.id
                in summaries[submission.id].assigned_editor_ids,
                "progress": summaries[submission.id].progress,
                **public_progress(submission.status, summaries[submission.id]),
            }
            for submission in submissions
        ]
    }


@router.get("/api/v1/editorial/editors")
def eligible_editors(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    if "site_admin" in _roles(actor) or "editor_in_chief" not in _roles(actor):
        raise HTTPException(
            status_code=403, detail="Only the Editor-in-Chief may assign editors."
        )
    candidates = db.scalars(
        select(User)
        .where(
            User.is_active.is_(True),
            User.roles.any(
                Role.name.in_(
                    ["editor_in_chief", "managing_editor", "associate_editor"]
                )
            ),
        )
        .order_by(User.display_name.asc())
    ).all()
    eligible = [
        user
        for user in candidates
        if "site_admin" not in _roles(user)
        and (
            user.id == actor.id
            or bool(_roles(user) & {"managing_editor", "associate_editor"})
        )
    ]
    return {
        "items": [
            {
                "id": str(user.id),
                "display_name": user.display_name,
                "email": user.email,
                "roles": sorted(_roles(user)),
            }
            for user in eligible
        ]
    }


@router.get("/api/v1/editorial/audit")
def editorial_audit(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    if "site_admin" in _roles(actor) or "editor_in_chief" not in _roles(actor):
        raise HTTPException(
            status_code=403,
            detail="Only the Editor-in-Chief may view editorial audit events.",
        )
    events = db.scalars(
        select(AuditEvent)
        .where(
            or_(
                AuditEvent.event_type.like("submission.%"),
                AuditEvent.event_type.like("editorial.%"),
                AuditEvent.event_type.like("review.%"),
                AuditEvent.event_type.like("publication.%"),
                AuditEvent.event_type.like("content.%"),
                AuditEvent.event_type.like("board.%"),
            )
        )
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
    ).all()
    items = []
    for event in events:
        event_actor = db.get(User, event.actor_id) if event.actor_id else None
        items.append(
            {
                "id": str(event.id),
                "event_type": event.event_type,
                "actor": event_actor.display_name if event_actor else "System",
                "target_type": event.target_type,
                "target_id": event.target_id,
                "created_at": event.created_at.isoformat(),
            }
        )
    return {"items": items}


@router.post(
    "/api/v1/editorial/submissions/{submission_id}/editors",
    dependencies=[Depends(require_csrf)],
)
def assign_editor(
    submission_id: uuid.UUID,
    payload: AssignEditorInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    if "site_admin" in _roles(actor) or "editor_in_chief" not in _roles(actor):
        raise HTTPException(
            status_code=403, detail="Only the Editor-in-Chief may assign editors."
        )
    submission = _editorial_submission(db, submission_id)
    editor = db.get(User, payload.editor_id)
    is_self_assignment = payload.editor_id == actor.id
    if (
        editor is None
        or not editor.is_active
        or "site_admin" in _roles(editor)
        or (
            not is_self_assignment
            and not (_roles(editor) & {"managing_editor", "associate_editor"})
        )
    ):
        raise HTTPException(
            status_code=422, detail="Select an active Managing or Associate Editor."
        )
    current = db.scalar(
        select(EditorAssignment).where(
            EditorAssignment.submission_id == submission.id,
            EditorAssignment.editor_id == editor.id,
            EditorAssignment.is_active.is_(True),
        )
    )
    if current is not None:
        current.can_make_decisions = payload.can_make_decisions
        assignment = current
    else:
        assignment = EditorAssignment(
            submission_id=submission.id,
            editor_id=editor.id,
            assigned_by_id=operator_id(db, actor.id),
            can_make_decisions=payload.can_make_decisions or is_self_assignment,
        )
        db.add(assignment)
    _audit(
        db,
        "editorial.editor_assigned",
        actor.id,
        "submission",
        submission.id,
        {"editor_id": str(editor.id), "decision_delegated": payload.can_make_decisions},
    )
    db.commit()
    return {"ok": True, "assignment_id": str(assignment.id)}


@router.post(
    "/api/v1/editorial/submissions/{submission_id}/transition",
    dependencies=[Depends(require_csrf)],
)
def transition_submission(
    submission_id: uuid.UUID,
    payload: TransitionInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    _active_editor_assignment(db, submission_id, editor.id)
    submission = _editorial_submission(db, submission_id)
    if payload.to_status not in manual_transitions(submission):
        raise HTTPException(409, "Use the review, decision or publication action. Review assignments cannot be bypassed.")
    _write_transition(db, submission, editor.id, payload.to_status, payload.reason)
    db.commit()
    return {"id": str(submission.id), "status": submission.status}


@router.post(
    "/api/v1/editorial/submissions/{submission_id}/reviewers",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def invite_reviewer(
    submission_id: uuid.UUID,
    payload: ReviewerInviteInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    _active_editor_assignment(db, submission_id, editor.id)
    submission = _editorial_submission(db, submission_id)
    if submission.status not in {
        "reviewer_invitation",
        "under_review",
        "editorial_screening",
    }:
        raise HTTPException(
            status_code=409,
            detail=(
                "Reviewers may only be assigned during editorial screening or review."
            ),
        )
    if payload.due_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=422, detail="The reviewer deadline must be in the future."
        )
    current_round = current_review_round(db, submission.id)
    if payload.round_number != current_round:
        raise HTTPException(
            status_code=409,
            detail=(
                "The review round changed. "
                "Refresh the case before assigning a reviewer."
            ),
        )
    if current_round == 1:
        manuscript_file = db.scalar(
            select(SubmissionFile)
            .where(
                SubmissionFile.submission_id == submission.id,
                SubmissionFile.scan_status == "clean",
            )
            .order_by(SubmissionFile.created_at.desc())
        )
    else:
        revision = db.scalar(
            select(SubmissionRevision).where(
                SubmissionRevision.submission_id == submission.id,
                SubmissionRevision.round_number == current_round - 1,
            )
        )
        manuscript_file = (
            db.get(SubmissionFile, revision.file_id) if revision is not None else None
        )
    if manuscript_file is None or manuscript_file.scan_status != "clean":
        raise HTTPException(
            status_code=409,
            detail="A clean manuscript file is required before reviewer assignment.",
        )
    if submission.status == "editorial_screening":
        _write_transition(
            db,
            submission,
            editor.id,
            "reviewer_invitation",
            "Reviewer invitation initiated.",
        )
    email = normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email))
    if user is not None and "reviewer" not in _roles(user):
        raise HTTPException(
            status_code=409,
            detail="This email already belongs to an account without a Reviewer role.",
        )
    profile = db.scalar(select(ReviewerProfile).where(ReviewerProfile.email == email))
    if profile is None:
        profile = ReviewerProfile(
            email=email,
            full_name=payload.full_name.strip(),
            affiliation=payload.affiliation,
            expertise=payload.expertise,
            languages=payload.languages,
            user_id=user.id if user else None,
            created_by_id=editor.id,
        )
        db.add(profile)
        db.flush()
    elif not profile.is_active:
        raise HTTPException(
            status_code=409, detail="This reviewer profile is deactivated."
        )

    existing = db.scalar(
        select(ReviewAssignment).where(
            ReviewAssignment.submission_id == submission.id,
            ReviewAssignment.reviewer_profile_id == profile.id,
            ReviewAssignment.round_number == current_round,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="This reviewer is already assigned for that round."
        )

    if user is None:
        require_delivery()
        pending_invitations = db.scalars(
            select(Invitation).where(
                Invitation.email == email,
                Invitation.used_at.is_(None),
                Invitation.expires_at > datetime.now(UTC),
            )
        ).all()
        for pending in pending_invitations:
            pending.used_at = datetime.now(UTC)
        token = new_one_time_secret()
        role = db.scalar(select(Role).where(Role.name == "reviewer"))
        if role is None:
            role = Role(name="reviewer")
            db.add(role)
            db.flush()
        db.add(
            Invitation(
                email=email,
                display_name=payload.full_name.strip(),
                role_id=role.id,
                token_hash=hash_secret(token),
                invited_by_id=operator_id(db, editor.id),
                expires_at=datetime.now(UTC)
                + timedelta(hours=get_settings().token_expiry_hours),
            )
        )
        base_url = get_settings().public_base_url.rstrip("/")
        link = f"{base_url}/accept-invitation#token={token}"
        queue_message(
            db, recipient=email, subject="NSAJ reviewer invitation", link=link
        )
    else:
        queue_message(
            db,
            recipient=email,
            subject="NSAJ review assignment",
            link=f"{get_settings().public_base_url.rstrip('/')}/sign-in",
        )
    review_assignment = ReviewAssignment(
        submission_id=submission.id,
        reviewer_profile_id=profile.id,
        reviewer_user_id=user.id if user else None,
        manuscript_file_id=manuscript_file.id,
        invited_by_id=operator_id(db, editor.id),
        round_number=current_round,
        due_at=payload.due_at,
    )
    db.add(review_assignment)
    _audit(
        db,
        "review.assignment_created",
        editor.id,
        "submission",
        submission.id,
        {
            "review_assignment_id": str(review_assignment.id),
            "round": current_round,
        },
    )
    db.commit()
    return {
        "ok": True,
        "assignment_id": str(review_assignment.id),
        "status": review_assignment.status,
    }


@router.post(
    "/api/v1/editorial/reviews/{assignment_id}/reminder",
    dependencies=[Depends(require_csrf)],
)
def send_reviewer_reminder(
    assignment_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    assignment = db.get(ReviewAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Review assignment not found.")
    _active_editor_assignment(db, assignment.submission_id, editor.id)
    if assignment.status not in {"invited", "accepted"}:
        raise HTTPException(
            status_code=409,
            detail="A reminder can only be sent for an active review assignment.",
        )
    require_delivery()
    profile = db.get(ReviewerProfile, assignment.reviewer_profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Reviewer profile not found.")
    queue_message(
        db,
        recipient=profile.email,
        subject="NSAJ review reminder",
        link=f"{get_settings().public_base_url.rstrip('/')}/sign-in",
    )
    _audit(
        db,
        "review.reminder_sent",
        editor.id,
        "review_assignment",
        assignment.id,
    )
    db.commit()
    return {"ok": True}


@router.get("/api/v1/editorial/submissions/{submission_id}")
def get_editorial_case(
    submission_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    editor_assignment = _active_editor_assignment(db, submission_id, editor.id)
    submission = _editorial_submission(db, submission_id)
    summary = load_editorial_summaries(db, [submission])[submission.id]
    files = db.scalars(
        select(SubmissionFile).where(SubmissionFile.submission_id == submission.id)
    ).all()
    assignments = db.scalars(
        select(ReviewAssignment)
        .where(ReviewAssignment.submission_id == submission.id)
        .order_by(ReviewAssignment.invited_at)
    ).all()
    reports = (
        {
            report.review_assignment_id: report
            for report in db.scalars(
                select(ReviewReport).where(
                    ReviewReport.review_assignment_id.in_(
                        [item.id for item in assignments]
                    )
                )
            ).all()
        }
        if assignments
        else {}
    )
    reminder_events = (
        db.scalars(
            select(AuditEvent).where(
                AuditEvent.event_type == "review.reminder_sent",
                AuditEvent.target_type == "review_assignment",
                AuditEvent.target_id.in_([str(item.id) for item in assignments]),
            )
        ).all()
        if assignments
        else []
    )
    reminders_by_assignment: dict[str, list[str]] = {}
    for event in reminder_events:
        if event.target_id:
            reminders_by_assignment.setdefault(event.target_id, []).append(
                event.created_at.isoformat()
            )
    reviews = []
    for assignment in assignments:
        profile = db.get(ReviewerProfile, assignment.reviewer_profile_id)
        report = reports.get(assignment.id)
        reviews.append(
            {
                "id": str(assignment.id),
                "round_number": assignment.round_number,
                "reviewer": profile.full_name if profile else "Unavailable reviewer",
                "email": profile.email if profile else None,
                "status": assignment.status,
                "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
                "conflict_status": assignment.conflict_status,
                "conflict_details": assignment.conflict_details,
                "recommendation": report.recommendation if report else None,
                "comments_to_editor": report.comments_to_editor if report else None,
                "comments_to_author": report.comments_to_author if report else None,
                "reminder_history": reminders_by_assignment.get(str(assignment.id), []),
            }
        )
    already_assigned_profiles = {
        item.reviewer_profile_id
        for item in assignments
        if item.round_number == summary.progress["current_round"]
    }
    reviewer_options = db.scalars(
        select(ReviewerProfile)
        .join(User, User.id == ReviewerProfile.user_id)
        .where(
            ReviewerProfile.is_active.is_(True),
            User.is_active.is_(True),
            User.roles.any(Role.name == "reviewer"),
            ~User.roles.any(Role.name == PRIVILEGED_CONFIDENTIAL_ROLE),
        )
        .order_by(ReviewerProfile.full_name, ReviewerProfile.email)
        .limit(500)
    ).all()
    return {
        "id": str(submission.id),
        "reference": submission.reference,
        "title": submission.title,
        "abstract": submission.abstract,
        "discipline": submission.discipline,
        "discipline_other": submission.discipline_other,
        "status": submission.status,
        "progress": summary.progress,
        **public_progress(submission.status, summary),
        "manual_transitions": manual_transitions(submission),
        "decision_options": [x for x in ["revision_requested", "accepted", "declined"] if x in TRANSITIONS.get(submission.status, set())],
        "can_record_decision": "editor_in_chief" in _roles(editor)
        or editor_assignment.can_make_decisions,
        "authors": [
            {
                "full_name": author.full_name,
                "affiliation": author.affiliation,
                "email": author.email,
            }
            for author in submission.authors
        ],
        "files": [
            {
                "id": str(item.id),
                "name": item.original_name,
                "scan_status": item.scan_status,
                "download_url": (
                    f"/api/v1/editorial/submissions/{submission.id}/files/{item.id}"
                    if item.scan_status == "clean"
                    else None
                ),
            }
            for item in files
        ],
        "reviews": reviews,
        "reviewer_options": [
            {
                "id": str(profile.id),
                "full_name": profile.full_name,
                "email": profile.email,
                "affiliation": profile.affiliation,
                "expertise": profile.expertise,
                "languages": profile.languages,
            }
            for profile in reviewer_options
            if profile.id not in already_assigned_profiles
        ],
        "workflow": [
            {
                "from": event.from_status,
                "to": event.to_status,
                "reason": event.reason,
                "created_at": event.created_at.isoformat(),
            }
            for event in db.scalars(
                select(SubmissionWorkflowEvent)
                .where(SubmissionWorkflowEvent.submission_id == submission.id)
                .order_by(SubmissionWorkflowEvent.created_at)
            ).all()
        ],
    }


@router.get("/api/v1/reviewer/assignments")
def reviewer_assignments(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    reviewer = _require_reviewer(actor)
    profile = _profile_for_user(db, reviewer)
    assignments = db.scalars(
        select(ReviewAssignment)
        .where(ReviewAssignment.reviewer_profile_id == profile.id)
        .order_by(ReviewAssignment.due_at)
    ).all()
    did_expire = False
    for item in assignments:
        did_expire = _expire_invitation(db, item) or did_expire
    if did_expire:
        db.commit()
    items = []
    for assignment in assignments:
        submission = db.get(Submission, assignment.submission_id)
        items.append(
            {
                "id": str(assignment.id),
                "reference": submission.reference if submission else "Unavailable",
                "title": submission.title if submission else "Unavailable",
                "status": assignment.status,
                "due_at": assignment.due_at.isoformat() if assignment.due_at else None,
                "round_number": assignment.round_number,
            }
        )
    order = {"invited": 0, "conflict_reported": 1, "accepted": 2, "completed": 3, "declined": 4, "expired": 5, "cancelled": 6}
    items.sort(key=lambda row: (order.get(row["status"], 7), row["due_at"] or "9999", row["id"]))
    return {"items": items}


@router.post(
    "/api/v1/reviewer/assignments/{assignment_id}/respond",
    dependencies=[Depends(require_csrf)],
)
def respond_to_review_invitation(
    assignment_id: uuid.UUID,
    payload: ReviewResponseInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    reviewer = _require_reviewer(actor)
    assignment = _review_assignment(db, assignment_id, reviewer)
    if _expire_invitation(db, assignment):
        db.commit()
        raise HTTPException(
            status_code=409, detail="The reviewer invitation has expired."
        )
    if assignment.status != "invited":
        raise HTTPException(
            status_code=409, detail="This invitation has already been answered."
        )
    if not payload.accept:
        assignment.status = "declined"
        assignment.declined_at = datetime.now(UTC)
    elif payload.has_conflict:
        if not payload.confidentiality_accepted:
            raise HTTPException(
                status_code=422, detail="Confidentiality acknowledgement is required."
            )
        if not payload.conflict_details.strip():
            raise HTTPException(
                status_code=422,
                detail="Describe the potential conflict for editorial resolution.",
            )
        assignment.status = "conflict_reported"
        assignment.conflict_status = "reported"
        assignment.conflict_details = payload.conflict_details.strip()
        assignment.accepted_at = datetime.now(UTC)
        assignment.confidentiality_accepted_at = datetime.now(UTC)
    else:
        if not payload.confidentiality_accepted:
            raise HTTPException(
                status_code=422, detail="Confidentiality acknowledgement is required."
            )
        assignment.status = "accepted"
        assignment.conflict_status = "clear"
        assignment.confidentiality_accepted_at = datetime.now(UTC)
        assignment.accepted_at = datetime.now(UTC)
        submission = db.get(Submission, assignment.submission_id)
        if submission and submission.status == "reviewer_invitation":
            _write_transition(
                db,
                submission,
                reviewer.id,
                "under_review",
                "Reviewer accepted the invitation.",
            )
    _audit(
        db,
        "review.invitation_answered",
        reviewer.id,
        "review_assignment",
        assignment.id,
        {"status": assignment.status, "conflict_status": assignment.conflict_status},
    )
    db.commit()
    return {"id": str(assignment.id), "status": assignment.status}


@router.post(
    "/api/v1/editorial/reviews/{assignment_id}/resolve-conflict",
    dependencies=[Depends(require_csrf)],
)
def resolve_review_conflict(
    assignment_id: uuid.UUID,
    clear: bool,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    assignment = db.get(ReviewAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=404, detail="Review assignment not found.")
    _active_editor_assignment(db, assignment.submission_id, editor.id)
    if assignment.conflict_status != "reported":
        raise HTTPException(
            status_code=409, detail="No unresolved conflict was reported."
        )
    assignment.conflict_status = "clear" if clear else "disqualifying"
    assignment.conflict_resolved_by_id = operator_id(db, editor.id)
    assignment.conflict_resolved_at = datetime.now(UTC)
    if clear:
        assignment.status = "accepted"
        assignment.confidentiality_accepted_at = datetime.now(UTC)
        submission = db.get(Submission, assignment.submission_id)
        if submission and submission.status == "reviewer_invitation":
            _write_transition(
                db,
                submission,
                editor.id,
                "under_review",
                "Conflict was reviewed and the assignment may proceed.",
            )
    else:
        assignment.status = "cancelled"
    _audit(
        db,
        "review.conflict_resolved",
        editor.id,
        "review_assignment",
        assignment.id,
        {"resolution": assignment.conflict_status},
    )
    db.commit()
    return {
        "id": str(assignment.id),
        "status": assignment.status,
        "conflict_status": assignment.conflict_status,
    }


@router.get("/api/v1/reviewer/assignments/{assignment_id}")
def get_assigned_manuscript(
    assignment_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    reviewer = _require_reviewer(actor)
    assignment = _review_assignment(db, assignment_id, reviewer)
    _require_review_access(assignment)
    submission = _editorial_submission(db, assignment.submission_id)
    if submission.status not in {"reviewer_invitation", "under_review"}:
        raise HTTPException(
            status_code=403,
            detail="This manuscript is no longer open for reviewer access.",
        )
    manuscript_file = (
        db.get(SubmissionFile, assignment.manuscript_file_id)
        if assignment.manuscript_file_id
        else None
    )
    review_model = get_settings().review_model
    return {
        "id": str(submission.id),
        "reference": submission.reference,
        "title": submission.title,
        "abstract": submission.abstract,
        "manuscript_type": submission.manuscript_type,
        "authors": (
            [
                {"full_name": item.full_name, "affiliation": item.affiliation}
                for item in submission.authors
            ]
            if review_model != "double_anonymous"
            else []
        ),
        "files": (
            [
                {
                    "id": str(manuscript_file.id),
                    "name": manuscript_file.original_name,
                    "url": (
                        f"/api/v1/reviewer/assignments/{assignment.id}/files/"
                        f"{manuscript_file.id}"
                    ),
                }
            ]
            if manuscript_file and manuscript_file.scan_status == "clean"
            else []
        ),
        "reviewer_identity_visibility": "hidden_from_author",
    }


@router.get("/api/v1/editorial/submissions/{submission_id}/files/{file_id}")
def download_editorial_manuscript(
    submission_id: uuid.UUID,
    file_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> FileResponse:
    editor = _require_editor(actor)
    _active_editor_assignment(db, submission_id, editor.id)
    submission = _editorial_submission(db, submission_id)
    file_record = db.scalar(
        select(SubmissionFile).where(
            SubmissionFile.id == file_id, SubmissionFile.submission_id == submission.id
        )
    )
    if file_record is None:
        raise HTTPException(status_code=404, detail="Manuscript file not found.")
    if file_record.scan_status != "clean":
        raise HTTPException(
            status_code=423,
            detail="This file is unavailable until it passes malware scanning.",
        )
    path = safe_private_path(file_record.storage_name)
    _audit(
        db,
        "editorial.manuscript_downloaded",
        editor.id,
        "submission_file",
        file_record.id,
        {"submission_id": str(submission.id)},
    )
    db.commit()
    return FileResponse(
        path,
        media_type=file_record.media_type,
        filename=file_record.original_name,
        headers={"Cache-Control": "private, no-store"},
    )


@router.get("/api/v1/reviewer/assignments/{assignment_id}/files/{file_id}")
def download_assigned_manuscript(
    assignment_id: uuid.UUID,
    file_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> FileResponse:
    reviewer = _require_reviewer(actor)
    assignment = _review_assignment(db, assignment_id, reviewer)
    _require_review_access(assignment)
    submission = _editorial_submission(db, assignment.submission_id)
    if submission.status not in {"reviewer_invitation", "under_review"}:
        raise HTTPException(
            status_code=403,
            detail="This manuscript is no longer open for reviewer access.",
        )
    file_record = (
        db.get(SubmissionFile, file_id)
        if assignment.manuscript_file_id == file_id
        else None
    )
    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    if file_record.scan_status != "clean":
        raise HTTPException(
            status_code=423,
            detail="This file is unavailable until it passes malware scanning.",
        )
    path = safe_private_path(file_record.storage_name)
    _audit(
        db,
        "review.manuscript_downloaded",
        reviewer.id,
        "review_assignment",
        assignment.id,
        {"file_id": str(file_record.id)},
    )
    db.commit()
    return FileResponse(
        path, media_type=file_record.media_type, filename=file_record.original_name
    )


@router.post(
    "/api/v1/reviewer/assignments/{assignment_id}/report",
    dependencies=[Depends(require_csrf)],
)
def submit_review_report(
    assignment_id: uuid.UUID,
    payload: ReviewReportInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    reviewer = _require_reviewer(actor)
    assignment = _review_assignment(db, assignment_id, reviewer)
    _require_review_access(assignment)
    if assignment.status != "accepted":
        raise HTTPException(
            status_code=409, detail="This assignment cannot receive a review report."
        )
    submission = db.get(Submission, assignment.submission_id)
    if (submission is None or submission.status not in {"under_review", "reviewer_invitation", "editorial_screening"}
        or assignment.round_number != current_review_round(db, assignment.submission_id)):
        raise HTTPException(409, "This review round is closed. Refresh your assignments.")
    report = ReviewReport(
        review_assignment_id=assignment.id,
        recommendation=payload.recommendation,
        comments_to_editor=payload.comments_to_editor,
        comments_to_author=payload.comments_to_author,
    )
    assignment.status = "completed"
    assignment.completed_at = datetime.now(UTC)
    db.add(report)
    _audit(
        db,
        "review.report_submitted",
        reviewer.id,
        "review_assignment",
        assignment.id,
        {"recommendation": report.recommendation},
    )
    db.commit()
    return {
        "ok": True,
        "recommendation": report.recommendation,
        "status": assignment.status,
    }


@router.post(
    "/api/v1/editorial/submissions/{submission_id}/decision",
    dependencies=[Depends(require_csrf)],
)
def make_editorial_decision(
    submission_id: uuid.UUID,
    payload: DecisionInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    assignment = _active_editor_assignment(db, submission_id, editor.id)
    if "editor_in_chief" not in _roles(editor) and not assignment.can_make_decisions:
        raise HTTPException(
            status_code=403,
            detail="Final decision authority was not delegated to this editor.",
        )
    submission = _editorial_submission(db, submission_id)
    current_round = current_review_round(db, submission.id)
    if payload.round_number != current_round:
        raise HTTPException(
            status_code=409,
            detail=(
                "The review round changed. "
                "Refresh the case before recording a decision."
            ),
        )
    existing = db.scalar(
        select(EditorialDecision).where(
            EditorialDecision.submission_id == submission.id,
            EditorialDecision.round_number == current_round,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="A decision is already recorded for this round."
        )
    if not payload.author_letter.strip():
        raise HTTPException(422, "An author decision letter is required.")
    remaining = db.scalars(select(ReviewAssignment).where(
        ReviewAssignment.submission_id == submission.id,
        ReviewAssignment.round_number == current_round,
        ReviewAssignment.status.in_(["invited", "accepted", "conflict_reported"]))).all()
    if remaining and (not payload.close_open_reviews or len(payload.review_closure_reason.strip()) < 3):
        raise HTTPException(409, "Reviews are outstanding. Wait for them or explicitly close them with a reason when recording your decision.")
    for review in remaining:
        review.status = "cancelled"
        _audit(db, "review.cancelled_by_decision", editor.id, "review_assignment", review.id,
               {"reason": payload.review_closure_reason})
    decision = EditorialDecision(
        submission_id=submission.id,
        editor_id=operator_id(db, editor.id),
        round_number=current_round,
        decision=payload.decision,
        author_letter=payload.author_letter,
        internal_reason=payload.internal_reason,
    )
    db.add(decision)
    _write_transition(
        db,
        submission,
        editor.id,
        payload.decision,
        payload.internal_reason or f"Decision recorded: {payload.decision}.",
    )
    _audit(
        db,
        "editorial.decision_recorded",
        editor.id,
        "submission",
        submission.id,
        {"decision": payload.decision, "round": current_round},
    )
    db.commit()
    return {
        "id": str(decision.id),
        "decision": decision.decision,
        "status": submission.status,
        "decided_at": decision.decided_at.isoformat() if decision.decided_at else None,
    }


@router.get("/api/v1/author/workspace")
def author_workspace(
    db: DB, actor: Annotated[User, Depends(get_author_user)]
) -> dict[str, list[dict]]:
    submissions = db.scalars(
        select(Submission)
        .where(
            Submission.submitting_author_id == actor.id, Submission.status != "draft"
        )
        .order_by(Submission.updated_at.desc())
    ).all()
    summaries = load_editorial_summaries(db, submissions)
    return {
        "items": [
            {
                "id": str(item.id),
                "reference": item.reference,
                "title": item.title,
                "status": item.status,
                **public_progress(item.status, summaries[item.id]),
                "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            }
            for item in submissions
        ]
    }


@router.get("/api/v1/author/submissions/{submission_id}/editorial")
def author_editorial_status(
    submission_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_author_user)],
) -> dict:
    submission = db.scalar(
        select(Submission).where(
            Submission.id == submission_id,
            Submission.submitting_author_id == actor.id,
            Submission.status != "draft",
        )
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    decisions = db.scalars(
        select(EditorialDecision)
        .where(EditorialDecision.submission_id == submission.id)
        .order_by(EditorialDecision.round_number)
    ).all()
    events = db.scalars(
        select(SubmissionWorkflowEvent)
        .where(SubmissionWorkflowEvent.submission_id == submission.id)
        .order_by(SubmissionWorkflowEvent.created_at)
    ).all()
    return {
        "id": str(submission.id),
        "reference": submission.reference,
        "title": submission.title,
        "status": submission.status,
        **public_progress(submission.status, load_editorial_summaries(db, [submission])[submission.id]),
        "decisions": [
            {
                "decision": item.decision,
                "round_number": item.round_number,
                "letter": item.author_letter,
                "decided_at": item.decided_at.isoformat(),
            }
            for item in decisions
        ],
        "history": [
            {"status": item.to_status, "created_at": item.created_at.isoformat()}
            for item in events
        ],
        "reviewer_identity_visibility": "hidden_from_author",
    }


@router.post(
    "/api/v1/author/submissions/{submission_id}/revisions",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def submit_revision(
    submission_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_author_user)],
    upload: Annotated[UploadFile, File()],
    response_note: Annotated[str, Form()] = "",
) -> dict:
    submission = db.scalar(
        select(Submission).where(
            Submission.id == submission_id, Submission.submitting_author_id == actor.id
        )
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="Submission not found.")
    if submission.status != "revision_requested":
        raise HTTPException(
            status_code=409, detail="This submission is not awaiting a revision."
        )
    stored = await store_upload(upload)
    file_record = SubmissionFile(
        submission_id=submission.id,
        storage_name=stored.storage_name,
        original_name=stored.original_name,
        media_type=stored.media_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        scan_status=stored.scan_status,
    )
    db.add(file_record)
    db.flush()
    if file_record.scan_status != "clean":
        db.commit()
        raise HTTPException(
            status_code=423,
            detail=(
                "The revision file is stored privately but cannot be submitted "
                "until scanning succeeds."
            ),
        )
    current_round = (
        db.scalar(
            select(SubmissionRevision.round_number)
            .where(SubmissionRevision.submission_id == submission.id)
            .order_by(SubmissionRevision.round_number.desc())
            .limit(1)
        )
        or 0
    )
    revision = SubmissionRevision(
        submission_id=submission.id,
        round_number=current_round + 1,
        author_id=actor.id,
        file_id=file_record.id,
        response_note=response_note[:4000],
    )
    db.add(revision)
    _write_transition(
        db,
        submission,
        actor.id,
        "resubmitted",
        f"Author resubmitted revision {revision.round_number}.",
    )
    _audit(
        db,
        "submission.revision_submitted",
        actor.id,
        "submission",
        submission.id,
        {"round": revision.round_number},
    )
    db.commit()
    return {
        "id": str(revision.id),
        "round_number": revision.round_number,
        "status": submission.status,
    }

class CancelReviewInput(StrictModel):
    reason: str = Field(min_length=3, max_length=4000)

@router.post("/api/v1/editorial/reviews/{assignment_id}/cancel", dependencies=[Depends(require_csrf)])
def cancel_review(assignment_id: uuid.UUID, payload: CancelReviewInput, db: DB,
                  actor: Annotated[User, Depends(get_authenticated_user)]):
    editor = _require_editor(actor)
    assignment = db.get(ReviewAssignment, assignment_id)
    if assignment is None: raise HTTPException(404, "Review assignment not found.")
    submission = _editorial_submission(db, assignment.submission_id)
    _active_editor_assignment(db, submission.id, editor.id)
    if assignment.round_number != current_review_round(db, submission.id) or assignment.status not in {"invited", "accepted", "conflict_reported"}:
        raise HTTPException(409, "Only an outstanding assignment in the current round can be cancelled.")
    if not payload.reason.strip(): raise HTTPException(422, "A cancellation reason is required.")
    assignment.status = "cancelled"
    _audit(db, "review.cancelled", editor.id, "review_assignment", assignment.id, {"reason": payload.reason})
    db.commit()
    return {"ok": True, "status": assignment.status}
