from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_author_user, require_csrf
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    AuditEvent,
    EmailIntake,
    Submission,
    SubmissionAuthor,
    SubmissionFile,
    User,
)
from app.services.content_schedule import utc
from app.services.email_intake import intake_available
from app.services.mail_delivery import valid_address
from app.services.manuscript_references import (
    ManuscriptReferenceUnavailable,
    allocate_manuscript_reference,
)
from app.services.security import hash_secret

router = APIRouter(tags=["email submissions"])
DB = Annotated[Session, Depends(get_db)]


class ClaimInput(BaseModel):
    token: str = Field(min_length=20, max_length=200)


@router.get("/api/v1/public/submission-options")
def submission_options():
    s = get_settings()
    ready = intake_available()
    return {
        "email_available": ready,
        "submission_email": s.submission_email if ready else None,
        "contact_email": s.journal_contact_email
        if valid_address(s.journal_contact_email)
        else None,
        "max_email_mb": s.max_intake_message_bytes // (1024 * 1024),
    }


@router.post("/api/v1/author/email-intake/claim", dependencies=[Depends(require_csrf)])
def claim_intake(
    payload: ClaimInput, db: DB, user: Annotated[User, Depends(get_author_user)]
):
    item = db.scalar(
        select(EmailIntake)
        .where(
            EmailIntake.token_hash == hash_secret(payload.token),
            EmailIntake.sender_email == user.email.casefold(),
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(404, "Email intake not found for this account.")
    if item.submission_id:
        submission = db.get(Submission, item.submission_id)
        return {
            "id": str(submission.id),
            "reference": submission.reference,
            "warnings": item.warnings,
        }
    if utc(item.expires_at) < datetime.now(UTC):
        raise HTTPException(
            410,
            "This intake link has expired. "
            "Email the manuscript again to receive a new link.",
        )
    try:
        reference = allocate_manuscript_reference(db)
    except ManuscriptReferenceUnavailable as exc:
        raise HTTPException(
            503, "A paper ID could not be allocated. Contact the journal administrator."
        ) from exc
    fields = item.metadata_fields
    submission = Submission(
        reference=reference,
        submitting_author_id=user.id,
        status="draft",
        title=item.title,
        abstract=fields.get("abstract", ""),
        keywords=fields.get("keywords", []),
        manuscript_type=fields.get("manuscript_type"),
        discipline=fields.get("discipline"),
        discipline_other=fields.get("discipline_other"),
        authors=[
            SubmissionAuthor(
                position=0,
                full_name=user.display_name,
                email=user.email,
                affiliation=fields.get("affiliation", ""),
            )
        ],
    )
    db.add(submission)
    db.flush()
    for file in item.files:
        if file["scan_status"] == "clean":
            db.add(SubmissionFile(submission_id=submission.id, **file))
    item.submission_id, item.claimed_at = submission.id, datetime.now(UTC)
    db.add(
        AuditEvent(
            actor_id=user.id,
            event_type="submission.email_claimed",
            target_type="submission",
            target_id=str(submission.id),
            details={"intake_id": str(item.id)},
        )
    )
    db.commit()
    return {"id": str(submission.id), "reference": reference, "warnings": item.warnings}
