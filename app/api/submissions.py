from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_author_user, require_csrf
from app.db.session import get_db
from app.models import AuditEvent, Submission, SubmissionAuthor, SubmissionFile, User
from app.services.manuscript_references import (
    ManuscriptReferenceUnavailable,
    allocate_manuscript_reference,
)
from app.services.private_files import safe_private_path, store_upload
from app.services.research_areas import Discipline

router = APIRouter(prefix="/api/v1/author/submissions", tags=["author submissions"])
DB = Annotated[Session, Depends(get_db)]
ManuscriptType = Literal[
    "original research", "review article", "case study", "technical paper"
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthorInput(StrictModel):
    full_name: str = Field(default="", max_length=200)
    affiliation: str = Field(default="", max_length=500)
    email: str | None = Field(default=None, max_length=320)

    @field_validator("full_name", "affiliation")
    @classmethod
    def trim_author_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("email", mode="before")
    @classmethod
    def normalize_optional_email(cls, value: str | None) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        return value


class DraftInput(StrictModel):
    title: str = Field(default="", max_length=500)
    abstract: str = Field(default="", max_length=50_000)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    manuscript_type: ManuscriptType | None = None
    discipline: Discipline | None = None
    discipline_other: str | None = Field(default=None, max_length=200)
    authors: list[AuthorInput] = Field(default_factory=list, max_length=50)


def _owned_submission(db: Session, submission_id: uuid.UUID, owner: User) -> Submission:
    submission = db.scalar(
        select(Submission)
        .where(
            Submission.id == submission_id,
            Submission.submitting_author_id == owner.id,
        )
        .with_for_update()
    )
    if submission is None:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return submission


def _draft_json(submission: Submission) -> dict:
    return {
        "id": str(submission.id),
        "reference": submission.reference,
        "status": submission.status,
        "title": submission.title,
        "abstract": submission.abstract,
        "keywords": submission.keywords,
        "manuscript_type": submission.manuscript_type,
        "discipline": submission.discipline,
        "discipline_other": submission.discipline_other,
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
                "id": str(file.id),
                "original_name": file.original_name,
                "size_bytes": file.size_bytes,
                "scan_status": file.scan_status,
                "created_at": file.created_at.isoformat() if file.created_at else None,
            }
            for file in submission.files
        ],
        "created_at": submission.created_at.isoformat()
        if submission.created_at
        else None,
        "updated_at": submission.updated_at.isoformat()
        if submission.updated_at
        else None,
    }


def _write_audit(
    db: Session, event: str, user: User, submission: Submission, **details: str
) -> None:
    db.add(
        AuditEvent(
            actor_id=user.id,
            event_type=event,
            target_type="submission",
            target_id=str(submission.id),
            details=details,
        )
    )


@router.get("")
def list_drafts(
    db: DB, user: Annotated[User, Depends(get_author_user)]
) -> dict[str, list[dict]]:
    submissions = db.scalars(
        select(Submission)
        .where(Submission.submitting_author_id == user.id, Submission.status == "draft")
        .order_by(Submission.updated_at.desc())
    ).all()
    return {"items": [_draft_json(submission) for submission in submissions]}


@router.post(
    "", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_csrf)]
)
def create_draft(
    payload: DraftInput, db: DB, user: Annotated[User, Depends(get_author_user)]
) -> dict:
    try:
        reference = allocate_manuscript_reference(db)
    except ManuscriptReferenceUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "A paper ID could not be allocated. Contact the journal administrator."
            ),
        ) from exc
    submission = Submission(
        reference=reference,
        submitting_author_id=user.id,
        status="draft",
        title=payload.title,
        abstract=payload.abstract,
        keywords=[word.strip() for word in payload.keywords if word.strip()],
        manuscript_type=payload.manuscript_type,
        discipline=payload.discipline,
        discipline_other=(payload.discipline_other or "").strip()
        if payload.discipline == "other"
        else None,
        authors=[
            SubmissionAuthor(position=index, **author.model_dump())
            for index, author in enumerate(payload.authors)
        ],
    )
    db.add(submission)
    db.flush()
    _write_audit(db, "submission.draft_created", user, submission)
    db.commit()
    db.refresh(submission)
    return _draft_json(submission)


@router.get("/{submission_id}")
def get_draft(
    submission_id: uuid.UUID,
    db: DB,
    user: Annotated[User, Depends(get_author_user)],
) -> dict:
    submission = _owned_submission(db, submission_id, user)
    if submission.status != "draft":
        raise HTTPException(status_code=404, detail="Draft not found.")
    return _draft_json(submission)


@router.patch("/{submission_id}", dependencies=[Depends(require_csrf)])
def update_draft(
    submission_id: uuid.UUID,
    payload: DraftInput,
    db: DB,
    user: Annotated[User, Depends(get_author_user)],
) -> dict:
    submission = _owned_submission(db, submission_id, user)
    if submission.status != "draft":
        raise HTTPException(status_code=409, detail="Only drafts can be edited.")
    submission.title = payload.title
    submission.abstract = payload.abstract
    submission.keywords = [word.strip() for word in payload.keywords if word.strip()]
    submission.manuscript_type = payload.manuscript_type
    if "discipline" in payload.model_fields_set:
        submission.discipline = payload.discipline
        submission.discipline_other = (
            (payload.discipline_other or "").strip()
            if payload.discipline == "other"
            else None
        )
    # The position has a per-submission unique constraint. Flush orphan deletes
    # before inserting replacement rows so an edit at position 0 cannot collide
    # with the previous author still occupying position 0.
    submission.authors.clear()
    db.flush()
    submission.authors = [
        SubmissionAuthor(position=index, **author.model_dump())
        for index, author in enumerate(payload.authors)
    ]
    _write_audit(db, "submission.draft_updated", user, submission)
    db.commit()
    db.refresh(submission)
    return _draft_json(submission)


@router.post(
    "/{submission_id}/files",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
async def upload_manuscript(
    submission_id: uuid.UUID,
    db: DB,
    user: Annotated[User, Depends(get_author_user)],
    upload: Annotated[UploadFile, File()],
) -> dict:
    submission = _owned_submission(db, submission_id, user)
    if submission.status != "draft":
        raise HTTPException(
            status_code=409, detail="Files can only be added to drafts."
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
    try:
        db.add(file_record)
        _write_audit(
            db,
            "submission.file_uploaded",
            user,
            submission,
            scan_status=stored.scan_status,
            size_bytes=str(stored.size_bytes),
        )
        db.commit()
    except Exception:
        db.rollback()
        stored.path.unlink(missing_ok=True)
        raise
    db.refresh(file_record)
    return {
        "id": str(file_record.id),
        "original_name": file_record.original_name,
        "size_bytes": file_record.size_bytes,
        "scan_status": file_record.scan_status,
        "download_available": file_record.scan_status == "clean",
    }


@router.get("/{submission_id}/files/{file_id}")
def download_manuscript(
    submission_id: uuid.UUID,
    file_id: uuid.UUID,
    db: DB,
    user: Annotated[User, Depends(get_author_user)],
) -> FileResponse:
    submission = _owned_submission(db, submission_id, user)
    file_record = db.scalar(
        select(SubmissionFile).where(
            SubmissionFile.id == file_id,
            SubmissionFile.submission_id == submission.id,
        )
    )
    if file_record is None:
        raise HTTPException(status_code=404, detail="File not found.")
    if file_record.scan_status != "clean":
        raise HTTPException(
            status_code=423,
            detail=("This file is unavailable until it passes malware scanning."),
        )
    path = safe_private_path(file_record.storage_name)
    _write_audit(
        db, "submission.file_downloaded", user, submission, file_id=str(file_record.id)
    )
    db.commit()
    return FileResponse(
        path, media_type=file_record.media_type, filename=file_record.original_name
    )
