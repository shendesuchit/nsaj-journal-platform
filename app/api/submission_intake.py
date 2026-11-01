"""Approved declaration versions and the draft-to-editorial handoff."""

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.auth import get_authenticated_user, get_author_user, require_csrf
from app.db.session import get_db
from app.models import (
    AuditEvent,
    Submission,
    SubmissionChecklist,
    SubmissionReceipt,
    SubmissionWorkflowEvent,
    User,
)
from app.services.private_files import safe_private_path

router = APIRouter(prefix="/api/v1", tags=["submission intake"])
DB = Annotated[Session, Depends(get_db)]


class ChecklistInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    declarations: list[str] = Field(min_length=1, max_length=30)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A checklist title is required.")
        return value.strip()

    @field_validator("declarations")
    @classmethod
    def declarations_valid(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value or len(value) > 4000 for value in cleaned):
            raise ValueError("Each declaration needs 1 to 4000 characters.")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Declarations must be distinct.")
        return cleaned


class SubmitInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    checklist_id: uuid.UUID
    acknowledged_indices: list[int] = Field(max_length=30)


def _chief(user: User) -> None:
    roles = {role.name for role in user.roles}
    if "editor_in_chief" not in roles or "site_admin" in roles:
        raise HTTPException(403, "Only the Editor-in-Chief may manage declarations.")


def _lock_policy(db: Session) -> None:
    # Serialize approvals and submission validation across API workers.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(72918421)"))


def _current(db: Session) -> SubmissionChecklist | None:
    return db.scalar(
        select(SubmissionChecklist)
        .where(SubmissionChecklist.approved_at.is_not(None))
        .order_by(SubmissionChecklist.approved_at.desc(), SubmissionChecklist.id.desc())
    )


def _json(item: SubmissionChecklist) -> dict:
    return {
        "id": str(item.id),
        "title": item.title,
        "declarations": item.declarations,
        "approved_at": item.approved_at.isoformat() if item.approved_at else None,
    }


def _audit(db: Session, actor: User, event: str, target: uuid.UUID) -> None:
    db.add(
        AuditEvent(
            actor_id=actor.id,
            event_type=event,
            target_type="submission_intake",
            target_id=str(target),
            details={},
        )
    )


@router.get("/editorial/submission-checklists")
def list_checklists(db: DB, actor: Annotated[User, Depends(get_authenticated_user)]):
    _chief(actor)
    return {
        "items": [
            _json(item)
            for item in db.scalars(
                select(SubmissionChecklist).order_by(
                    SubmissionChecklist.created_at.desc()
                )
            ).all()
        ]
    }


@router.post(
    "/editorial/submission-checklists",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_checklist(
    payload: ChecklistInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
):
    _chief(actor)
    item = SubmissionChecklist(**payload.model_dump(), created_by_id=actor.id)
    db.add(item)
    db.flush()
    _audit(db, actor, "submission.checklist_created", item.id)
    db.commit()
    return _json(item)


@router.post(
    "/editorial/submission-checklists/{checklist_id}/approve",
    dependencies=[Depends(require_csrf)],
)
def approve_checklist(
    checklist_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
):
    _chief(actor)
    _lock_policy(db)
    item = db.get(SubmissionChecklist, checklist_id)
    if item is None:
        raise HTTPException(404, "Checklist not found.")
    if item.approved_at is not None:
        raise HTTPException(409, "An approved version cannot be approved again.")
    item.approved_at = datetime.now(UTC)
    item.approved_by_id = actor.id
    _audit(db, actor, "submission.checklist_approved", item.id)
    db.commit()
    return _json(item)


@router.get("/author/submission-checklist")
def current_checklist(db: DB, actor: Annotated[User, Depends(get_author_user)]):
    item = _current(db)
    return {"checklist": _json(item) if item else None}


@router.post(
    "/author/submissions/{submission_id}/submit", dependencies=[Depends(require_csrf)]
)
def submit(
    submission_id: uuid.UUID,
    payload: SubmitInput,
    db: DB,
    actor: Annotated[User, Depends(get_author_user)],
):
    _lock_policy(db)
    item = db.scalar(
        select(Submission)
        .where(
            Submission.id == submission_id, Submission.submitting_author_id == actor.id
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(404, "Submission not found.")
    if item.status != "draft":
        raise HTTPException(409, "This manuscript has already left the draft stage.")
    checklist = _current(db)
    if checklist is None or checklist.id != payload.checklist_id:
        raise HTTPException(
            409, "The approved checklist changed. Reload and confirm it."
        )
    expected = list(range(len(checklist.declarations)))
    if sorted(payload.acknowledged_indices) != expected:
        raise HTTPException(422, "Confirm every declaration exactly once.")
    missing_details = []
    if not item.title.strip():
        missing_details.append("manuscript title")
    if not item.manuscript_type:
        missing_details.append("manuscript type")
    if not item.discipline:
        missing_details.append("area of research")
    if item.discipline == "other" and not (item.discipline_other or "").strip():
        missing_details.append("other area of research")
    if not item.abstract.strip():
        missing_details.append("abstract")
    if not item.keywords:
        missing_details.append("at least one keyword")
    if not item.authors:
        missing_details.append("at least one author")
    for index, author in enumerate(item.authors, start=1):
        if not author.full_name.strip():
            missing_details.append(f"author {index} name")
        if not author.affiliation.strip():
            missing_details.append(f"author {index} affiliation")
    if missing_details:
        raise HTTPException(
            422,
            "Complete these required details before final submission: "
            + ", ".join(missing_details)
            + ".",
        )
    if not item.files or any(file.scan_status != "clean" for file in item.files):
        raise HTTPException(
            423,
            "Upload at least one manuscript file and wait until every uploaded "
            "file has a clean scan.",
        )
    try:
        for file in item.files:
            safe_private_path(file.storage_name)
    except HTTPException as exc:
        raise HTTPException(
            423, "A manuscript file is unavailable. Upload it again."
        ) from exc
    now = datetime.now(UTC)
    receipt = SubmissionReceipt(
        submission_id=item.id,
        checklist_id=checklist.id,
        author_id=actor.id,
        declarations=list(checklist.declarations),
        submitted_at=now,
        manuscript_snapshot={
            "reference": item.reference,
            "title": item.title,
            "abstract": item.abstract,
            "keywords": item.keywords,
            "manuscript_type": item.manuscript_type,
            "discipline": item.discipline,
            "discipline_other": item.discipline_other,
            "authors": [
                {
                    "full_name": a.full_name,
                    "affiliation": a.affiliation,
                    "email": a.email,
                }
                for a in item.authors
            ],
            "files": [{"id": str(f.id), "sha256": f.sha256} for f in item.files],
        },
    )
    db.add(receipt)
    item.status = "submitted"
    db.add(
        SubmissionWorkflowEvent(
            submission_id=item.id,
            actor_id=actor.id,
            from_status="draft",
            to_status="submitted",
            reason="Author confirmed approved declarations.",
        )
    )
    _audit(db, actor, "submission.submitted", item.id)
    db.commit()
    return {
        "id": str(item.id),
        "reference": item.reference,
        "status": item.status,
        "submitted_at": now.isoformat(),
    }


@router.get("/author/submissions/{submission_id}/receipt")
def submission_receipt(
    submission_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_author_user)],
):
    result = db.execute(
        select(SubmissionReceipt, Submission.reference)
        .join(Submission, Submission.id == SubmissionReceipt.submission_id)
        .where(
            SubmissionReceipt.submission_id == submission_id,
            SubmissionReceipt.author_id == actor.id,
            Submission.submitting_author_id == actor.id,
        )
    ).one_or_none()
    if result is None:
        raise HTTPException(404, "Submission receipt not found.")
    receipt, reference = result
    return {
        "reference": receipt.manuscript_snapshot.get("reference", reference),
        "checklist_id": str(receipt.checklist_id),
        "declarations": receipt.declarations,
        "submitted_at": receipt.submitted_at.isoformat(),
    }
