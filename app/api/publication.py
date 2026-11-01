from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import get_authenticated_user, require_csrf
from app.api.editorial import _active_editor_assignment, _require_editor, _roles
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    Article,
    ArticleAuthor,
    ArticleHistory,
    ArticleScholarlyAction,
    AuditEvent,
    EditorAssignment,
    Issue,
    Submission,
    SubmissionAuthor,
    SubmissionFile,
    SubmissionWorkflowEvent,
    User,
    Volume,
)
from app.services.accountability import audit_details, operator_id
from app.services.private_files import safe_private_path
from app.services.research_areas import RESEARCH_AREAS, Discipline

router = APIRouter(tags=["publication"])
DB = Annotated[Session, Depends(get_db)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VolumeInput(StrictModel):
    number: int = Field(ge=1, le=999)
    year: int = Field(ge=1900, le=2200)
    title: str = Field(default="", max_length=300)


class IssueInput(StrictModel):
    volume_id: uuid.UUID
    number: str = Field(min_length=1, max_length=50)
    title: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=10_000)


class VolumeStatusInput(StrictModel):
    status: Literal["open", "closed", "archived"]
    expected_status: Literal["open", "closed", "archived"]


class IssueVolumeInput(StrictModel):
    volume_id: uuid.UUID


class VolumeOrderInput(StrictModel):
    volume_ids: list[uuid.UUID] = Field(max_length=1000)


class DraftIssueOrderInput(StrictModel):
    issue_ids: list[uuid.UUID] = Field(max_length=1000)


class ArticleInput(StrictModel):
    slug: str = Field(min_length=3, max_length=220)
    title: str = Field(min_length=1, max_length=500)
    abstract: str = Field(min_length=1, max_length=50_000)
    final_file_id: uuid.UUID
    references_text: str = Field(default="", max_length=30_000)
    funding: str = Field(default="", max_length=10_000)
    acknowledgements: str = Field(default="", max_length=10_000)
    license: str | None = Field(default=None, max_length=300)
    doi: str | None = Field(default=None, max_length=300)
    article_number: str | None = Field(default=None, max_length=50)
    page_range: str | None = Field(default=None, max_length=50)

    @field_validator("slug")
    @classmethod
    def slug_must_be_stable_path_segment(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
            raise ValueError(
                "Use lowercase letters, numbers, and single hyphens in the slug"
            )
        return value


class VerifyValueInput(StrictModel):
    evidence_reference: str = Field(min_length=3, max_length=500)


class VerifyDoiInput(StrictModel):
    evidence_reference: str | None = Field(default=None, min_length=3, max_length=500)


class ArticleIssueInput(StrictModel):
    issue_id: uuid.UUID


class IssueScheduleInput(StrictModel):
    scheduled_at: datetime

    @field_validator("scheduled_at")
    @classmethod
    def schedule_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("scheduled_at must include a timezone")
        return value.astimezone(UTC)


class ArticleActionInput(StrictModel):
    action_type: Literal[
        "correction", "expression_of_concern", "retraction", "withdrawal"
    ]
    statement: str = Field(min_length=1, max_length=20_000)
    publish_public_notice: bool = False


def _manager(user: User) -> User:
    roles = _roles(user)
    if not (
        roles & {"site_admin", "editor_in_chief", "managing_editor", "associate_editor"}
    ):
        raise HTTPException(
            status_code=403, detail="A journal content management role is required."
        )
    return user


def _audit(
    db: Session,
    event: str,
    actor_id: uuid.UUID,
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


def _require_case_editor(
    db: Session, submission: Submission, actor: User
) -> EditorAssignment:
    editor = _require_editor(actor)
    return _active_editor_assignment(db, submission.id, editor.id)


def _issue_public(issue_id: uuid.UUID, db: Session) -> Issue | None:
    now = datetime.now(UTC)
    issue = db.get(Issue, issue_id)
    if issue is None or issue.status != "published" or issue.published_at is None:
        return None
    published_at = issue.published_at
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    if published_at > now:
        return None
    return issue


def _public_article_json(article: Article, db: Session) -> dict:
    issue = _issue_public(article.issue_id, db) if article.issue_id else None
    volume = db.get(Volume, issue.volume_id) if issue else None
    reference = db.scalar(
        select(Submission.reference).where(Submission.id == article.submission_id)
    )
    authors = db.scalars(
        select(ArticleAuthor)
        .where(ArticleAuthor.article_id == article.id)
        .order_by(ArticleAuthor.position)
    ).all()
    action = db.scalar(
        select(ArticleScholarlyAction)
        .where(
            ArticleScholarlyAction.article_id == article.id,
            ArticleScholarlyAction.status == "published",
        )
        .order_by(
            (ArticleScholarlyAction.action_type == "retraction").desc(),
            ArticleScholarlyAction.created_at.desc(),
        )
    )
    return {
        "id": str(article.id),
        "manuscript_reference": reference,
        "slug": article.slug,
        "title": article.title,
        "abstract": article.abstract,
        "keywords": article.keywords,
        "manuscript_type": article.manuscript_type,
        "discipline": article.discipline,
        "discipline_other": article.discipline_other,
        "authors": [
            {
                "full_name": item.full_name,
                "affiliation": item.affiliation,
                "orcid": item.orcid,
            }
            for item in authors
        ],
        "published_at": article.published_at.isoformat()
        if article.published_at
        else None,
        "volume": {"number": volume.number, "year": volume.year, "title": volume.title}
        if volume
        else None,
        "issue": {"number": issue.number, "title": issue.title} if issue else None,
        "article_number": article.article_number,
        "page_range": article.page_range,
        "doi": article.doi if article.doi_verified else None,
        "license": article.license if article.license_verified else None,
        "file_url": f"/api/v1/public/articles/{article.slug}/file"
        if article.final_file_id
        and not db.scalar(
            select(ArticleScholarlyAction.id).where(
                ArticleScholarlyAction.article_id == article.id,
                ArticleScholarlyAction.action_type == "retraction",
                ArticleScholarlyAction.status == "published",
            )
        )
        else None,
        "citation": _citation(article, authors, issue, volume),
        "publication_notice": {
            "type": action.action_type,
            "statement": action.statement,
        }
        if action
        else None,
    }


def _citation(
    article: Article,
    authors: list[ArticleAuthor],
    issue: Issue | None,
    volume: Volume | None,
) -> str:
    author_names = ", ".join(item.full_name for item in authors)
    journal_part = "Noble Scientific Advances Journal"
    if volume:
        journal_part += f", vol. {volume.number} ({volume.year})"
    if issue:
        journal_part += f", no. {issue.number}"
    suffix = f", pp. {article.page_range}" if article.page_range else ""
    doi = (
        f" https://doi.org/{article.doi}"
        if article.doi_verified and article.doi
        else ""
    )
    return f"{author_names}. {article.title}. {journal_part}{suffix}.{doi}".strip()


@router.post(
    "/api/v1/admin/volumes", status_code=201, dependencies=[Depends(require_csrf)]
)
def create_volume(
    payload: VolumeInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    volume = Volume(
        number=payload.number,
        year=payload.year,
        title=payload.title,
        status="open",
        display_order=(db.scalar(select(func.min(Volume.display_order))) or 0) - 1,
        created_by_id=manager.id,
    )
    db.add(volume)
    _audit(
        db,
        "publication.volume_created",
        manager.id,
        "volume",
        volume.id,
        {"year": volume.year, "number": volume.number},
    )
    db.commit()
    return {
        "id": str(volume.id),
        "number": volume.number,
        "year": volume.year,
        "status": volume.status,
    }


@router.put(
    "/api/v1/admin/volumes/{volume_id}/status",
    dependencies=[Depends(require_csrf)],
)
def update_volume_status(
    volume_id: uuid.UUID,
    payload: VolumeStatusInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    volume = db.scalar(select(Volume).where(Volume.id == volume_id).with_for_update())
    if volume is None:
        raise HTTPException(404, "Volume not found.")
    if volume.status != payload.expected_status:
        raise HTTPException(409, "Volume changed. Refresh before updating its status.")
    transitions = {
        "open": {"closed"},
        "closed": {"open", "archived"},
        "archived": {"closed"},
    }
    if payload.status not in transitions[volume.status]:
        raise HTTPException(
            409, "Close a volume before archiving; restore it before reopening."
        )
    if payload.status == "archived" and db.scalar(
        select(Issue.id)
        .where(Issue.volume_id == volume.id, Issue.status != "published")
        .limit(1)
    ):
        raise HTTPException(
            409, "Complete or move unpublished issues before archiving this volume."
        )
    previous = volume.status
    volume.status = payload.status
    _audit(
        db,
        "publication.volume_status_changed",
        manager.id,
        "volume",
        volume.id,
        {"from_status": previous, "to_status": volume.status},
    )
    db.commit()
    return {"id": str(volume.id), "status": volume.status}


@router.get("/api/v1/admin/volumes")
def list_volumes(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    _manager(actor)
    volumes = db.scalars(
        select(Volume).order_by(
            Volume.display_order, Volume.year.desc(), Volume.number.desc()
        )
    ).all()
    issues = db.scalars(select(Issue)).all()
    issues_by_volume: dict[uuid.UUID, list[Issue]] = {}
    for issue in issues:
        issues_by_volume.setdefault(issue.volume_id, []).append(issue)
    return {
        "items": [
            {
                "id": str(item.id),
                "number": item.number,
                "year": item.year,
                "title": item.title,
                "status": item.status,
                "display_order": item.display_order,
                "issues": [
                    {
                        "id": str(issue.id),
                        "number": issue.number,
                        "title": issue.title,
                        "status": issue.status,
                        "display_order": issue.display_order,
                        "scheduled_at": issue.scheduled_at.isoformat()
                        if issue.scheduled_at
                        else None,
                        "published_at": issue.published_at.isoformat()
                        if issue.published_at
                        else None,
                    }
                    for issue in sorted(
                        issues_by_volume.get(item.id, []),
                        key=lambda value: (
                            value.display_order,
                            not value.number.isdigit(),
                            int(value.number)
                            if value.number.isdigit()
                            else value.number.casefold(),
                        ),
                    )
                ],
            }
            for item in volumes
        ]
    }


@router.get("/api/v1/admin/production-articles")
def list_production_articles(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    manager = _manager(actor)
    if "site_admin" in _roles(manager):
        raise HTTPException(
            status_code=403,
            detail="Site Admin accounts cannot access confidential production records.",
        )

    assigned_submissions = select(EditorAssignment.submission_id).where(
        EditorAssignment.editor_id == manager.id,
        EditorAssignment.is_active.is_(True),
    )
    rows = db.execute(
        select(Article, Submission.reference)
        .join(Submission, Submission.id == Article.submission_id)
        .where(
            Article.status.in_(("production", "scheduled")),
            Submission.id.in_(assigned_submissions),
        )
        .order_by(Submission.reference, Article.title)
    ).all()
    return {
        "items": [
            {
                "id": str(article.id),
                "reference": reference,
                "title": article.title,
                "status": article.status,
                "issue_id": str(article.issue_id) if article.issue_id else None,
            }
            for article, reference in rows
        ]
    }


@router.put(
    "/api/v1/admin/volumes/order",
    dependencies=[Depends(require_csrf)],
)
def reorder_volumes(
    payload: VolumeOrderInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    volumes = db.scalars(
        select(Volume)
        .order_by(Volume.display_order, Volume.year.desc(), Volume.number.desc())
        .with_for_update()
    ).all()
    current_ids = [volume.id for volume in volumes]
    if len(payload.volume_ids) != len(current_ids) or set(payload.volume_ids) != set(
        current_ids
    ):
        raise HTTPException(
            status_code=409,
            detail="Refresh the volume list and try reordering again.",
        )

    by_id = {volume.id: volume for volume in volumes}
    for position, volume_id in enumerate(payload.volume_ids):
        by_id[volume_id].display_order = position
    _audit(
        db,
        "publication.volume_order_changed",
        manager.id,
        "volume_collection",
        "all",
        {"volume_ids": [str(volume_id) for volume_id in payload.volume_ids]},
    )
    db.commit()
    return {"volume_ids": [str(volume_id) for volume_id in payload.volume_ids]}


@router.put(
    "/api/v1/admin/volumes/{volume_id}/issues/order",
    dependencies=[Depends(require_csrf)],
)
def reorder_draft_issues(
    volume_id: uuid.UUID,
    payload: DraftIssueOrderInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    volume = db.scalar(select(Volume).where(Volume.id == volume_id).with_for_update())
    if volume is None:
        raise HTTPException(status_code=404, detail="Volume not found.")
    issues = db.scalars(
        select(Issue)
        .where(Issue.volume_id == volume.id)
        .order_by(Issue.display_order, Issue.number)
        .with_for_update()
    ).all()
    drafts = [issue for issue in issues if issue.status == "draft"]
    if len(payload.issue_ids) != len(drafts) or set(payload.issue_ids) != {
        issue.id for issue in drafts
    }:
        raise HTTPException(
            status_code=409,
            detail="Refresh this volume and try reordering its draft issues again.",
        )

    ordered_drafts = iter(payload.issue_ids)
    draft_by_id = {issue.id: issue for issue in drafts}
    for position, issue in enumerate(issues):
        if issue.status == "draft":
            issue = draft_by_id[next(ordered_drafts)]
        issue.display_order = position
    _audit(
        db,
        "publication.draft_issue_order_changed",
        manager.id,
        "volume",
        volume.id,
        {"draft_issue_ids": [str(issue_id) for issue_id in payload.issue_ids]},
    )
    db.commit()
    return {"issue_ids": [str(issue_id) for issue_id in payload.issue_ids]}


@router.put(
    "/api/v1/admin/issues/{issue_id}/volume",
    dependencies=[Depends(require_csrf)],
)
def move_issue_to_volume(
    issue_id: uuid.UUID,
    payload: IssueVolumeInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    if issue.status != "draft":
        raise HTTPException(
            status_code=409,
            detail="Only draft issues can be moved between volumes.",
        )

    destination = db.scalar(
        select(Volume).where(Volume.id == payload.volume_id).with_for_update()
    )
    if destination is None:
        raise HTTPException(status_code=404, detail="Destination volume not found.")
    if destination.status != "open":
        raise HTTPException(
            status_code=409,
            detail="The destination volume is closed and cannot receive issues.",
        )

    previous_volume_id = issue.volume_id
    if previous_volume_id == destination.id:
        return {
            "id": str(issue.id),
            "volume_id": str(destination.id),
            "status": issue.status,
            "unchanged": True,
        }

    duplicate = db.scalar(
        select(Issue.id).where(
            Issue.volume_id == destination.id,
            Issue.number == issue.number,
            Issue.id != issue.id,
        )
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Issue {issue.number} already exists in Volume "
                f"{destination.number} ({destination.year})."
            ),
        )

    issue.volume_id = destination.id
    destination_max_order = db.scalar(
        select(func.max(Issue.display_order)).where(Issue.volume_id == destination.id)
    )
    issue.display_order = (
        0 if destination_max_order is None else destination_max_order + 1
    )
    _audit(
        db,
        "publication.issue_moved",
        manager.id,
        "issue",
        issue.id,
        {
            "issue_number": issue.number,
            "from_volume_id": str(previous_volume_id),
            "to_volume_id": str(destination.id),
        },
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                f"Issue {issue.number} already exists in Volume "
                f"{destination.number} ({destination.year})."
            ),
        ) from error
    return {
        "id": str(issue.id),
        "volume_id": str(destination.id),
        "status": issue.status,
        "unchanged": False,
    }


@router.post(
    "/api/v1/admin/issues", status_code=201, dependencies=[Depends(require_csrf)]
)
def create_issue(
    payload: IssueInput, db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict:
    manager = _manager(actor)
    volume = db.scalar(
        select(Volume).where(Volume.id == payload.volume_id).with_for_update()
    )
    if volume is None or volume.status != "open":
        raise HTTPException(status_code=409, detail="Select an open volume.")
    current_max_order = db.scalar(
        select(func.max(Issue.display_order)).where(Issue.volume_id == volume.id)
    )
    issue = Issue(
        volume_id=volume.id,
        number=payload.number.strip(),
        title=payload.title,
        description=payload.description,
        status="draft",
        display_order=0 if current_max_order is None else current_max_order + 1,
        created_by_id=manager.id,
    )
    db.add(issue)
    _audit(
        db,
        "publication.issue_created",
        manager.id,
        "issue",
        issue.id,
        {"volume_id": str(volume.id)},
    )
    db.commit()
    return {"id": str(issue.id), "number": issue.number, "status": issue.status}


@router.post(
    "/api/v1/editorial/submissions/{submission_id}/article",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_production_article(
    submission_id: uuid.UUID,
    payload: ArticleInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    _active_editor_assignment(db, submission_id, editor.id)
    submission = db.get(Submission, submission_id)
    if submission is None or submission.status != "accepted":
        raise HTTPException(
            status_code=409, detail="Only accepted submissions can enter production."
        )
    if (
        db.scalar(select(Article.id).where(Article.submission_id == submission.id))
        is not None
    ):
        raise HTTPException(
            status_code=409,
            detail="A production article already exists for this submission.",
        )
    file_record = db.scalar(
        select(SubmissionFile).where(
            SubmissionFile.id == payload.final_file_id,
            SubmissionFile.submission_id == submission.id,
        )
    )
    if file_record is None or file_record.scan_status != "clean":
        raise HTTPException(
            status_code=422, detail="Select a clean file belonging to this submission."
        )
    authors = db.scalars(
        select(SubmissionAuthor)
        .where(SubmissionAuthor.submission_id == submission.id)
        .order_by(SubmissionAuthor.position)
    ).all()
    if not authors:
        raise HTTPException(
            status_code=422,
            detail="At least one author is required for production metadata.",
        )
    article = Article(
        submission_id=submission.id,
        slug=payload.slug,
        title=payload.title.strip(),
        abstract=payload.abstract.strip(),
        keywords=submission.keywords,
        manuscript_type=submission.manuscript_type,
        discipline=submission.discipline,
        discipline_other=submission.discipline_other,
        final_file_id=file_record.id,
        references_text=payload.references_text,
        funding=payload.funding,
        acknowledgements=payload.acknowledgements,
        license=payload.license,
        doi=payload.doi,
        article_number=payload.article_number,
        page_range=payload.page_range,
        status="production",
        created_by_id=operator_id(db, editor.id),
    )
    db.add(article)
    db.flush()
    db.add_all(
        [
            ArticleAuthor(
                article_id=article.id,
                position=index,
                full_name=item.full_name,
                affiliation=item.affiliation,
            )
            for index, item in enumerate(authors)
        ]
    )
    previous = submission.status
    submission.status = "production"
    db.add(
        SubmissionWorkflowEvent(
            submission_id=submission.id,
            actor_id=operator_id(db, editor.id),
            from_status=previous,
            to_status="production",
            reason="Accepted manuscript entered production.",
        )
    )
    db.add(
        ArticleHistory(
            article_id=article.id,
            actor_id=operator_id(db, editor.id),
            event_type="production_created",
            details={"submission_id": str(submission.id)},
        )
    )
    _audit(
        db,
        "publication.article_created",
        editor.id,
        "article",
        article.id,
        {"submission_id": str(submission.id)},
    )
    db.commit()
    return {"id": str(article.id), "slug": article.slug, "status": article.status}


@router.post(
    "/api/v1/editorial/articles/{article_id}/license/verify",
    dependencies=[Depends(require_csrf)],
)
def verify_article_license(
    article_id: uuid.UUID,
    payload: VerifyValueInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found.")
    _active_editor_assignment(db, article.submission_id, editor.id)
    if not article.license:
        raise HTTPException(
            status_code=409, detail="Add approved license text before verification."
        )
    article.license_verified = True
    article.license_verified_by_id = operator_id(db, editor.id)
    article.license_verified_at = datetime.now(UTC)
    db.add(
        ArticleHistory(
            article_id=article.id,
            actor_id=operator_id(db, editor.id),
            event_type="license_verified",
            details={"evidence_reference": payload.evidence_reference},
        )
    )
    _audit(db, "publication.license_verified", editor.id, "article", article.id)
    db.commit()
    return {"ok": True, "license_verified": True}


@router.post(
    "/api/v1/editorial/articles/{article_id}/doi/verify",
    dependencies=[Depends(require_csrf)],
)
def verify_article_doi(
    article_id: uuid.UUID,
    payload: VerifyDoiInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found.")
    _active_editor_assignment(db, article.submission_id, editor.id)
    if not article.doi:
        if get_settings().app_env.casefold() in {"development", "test"}:
            return {
                "ok": True,
                "doi_verified": False,
                "skipped": True,
                "message": "No DOI is registered; DOI verification was skipped.",
            }
        raise HTTPException(
            status_code=409,
            detail="Add a DOI value before recording registration evidence.",
        )
    if not payload.evidence_reference:
        raise HTTPException(
            status_code=422,
            detail=(
                "A registration evidence reference is required when a DOI is present."
            ),
        )
    article.doi_verified = True
    article.doi_registration_reference = payload.evidence_reference
    article.doi_verified_by_id = operator_id(db, editor.id)
    article.doi_verified_at = datetime.now(UTC)
    db.add(
        ArticleHistory(
            article_id=article.id,
            actor_id=operator_id(db, editor.id),
            event_type="doi_registration_verified",
            details={"evidence_reference": payload.evidence_reference},
        )
    )
    _audit(db, "publication.doi_verified", editor.id, "article", article.id)
    db.commit()
    return {"ok": True, "doi_verified": True}


@router.put(
    "/api/v1/editorial/articles/{article_id}/issue",
    dependencies=[Depends(require_csrf)],
)
def assign_article_to_issue(
    article_id: uuid.UUID,
    payload: ArticleIssueInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found.")
    _active_editor_assignment(db, article.submission_id, editor.id)
    if article.status not in {"production", "scheduled"}:
        raise HTTPException(
            status_code=409,
            detail="Only production-ready articles can be assigned to an issue.",
        )
    issue = db.get(Issue, payload.issue_id)
    if issue is None or issue.status not in {"draft", "scheduled"}:
        raise HTTPException(
            status_code=409, detail="Select a draft or scheduled issue."
        )
    article.issue_id = issue.id
    db.add(
        ArticleHistory(
            article_id=article.id,
            actor_id=operator_id(db, editor.id),
            event_type="issue_assigned",
            details={"issue_id": str(issue.id)},
        )
    )
    _audit(
        db,
        "publication.article_assigned",
        editor.id,
        "article",
        article.id,
        {"issue_id": str(issue.id)},
    )
    db.commit()
    return {"ok": True, "issue_id": str(issue.id)}


@router.post(
    "/api/v1/editorial/issues/{issue_id}/schedule", dependencies=[Depends(require_csrf)]
)
def schedule_issue(
    issue_id: uuid.UUID,
    payload: IssueScheduleInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    issue = db.get(Issue, issue_id)
    if issue is None or issue.status != "draft":
        raise HTTPException(
            status_code=409, detail="Only a draft issue can be scheduled."
        )
    articles = db.scalars(select(Article).where(Article.issue_id == issue.id)).all()
    if not articles:
        raise HTTPException(
            status_code=409,
            detail="Add at least one article before scheduling the issue.",
        )
    for article in articles:
        _active_editor_assignment(db, article.submission_id, editor.id)
    issue.status = "scheduled"
    issue.scheduled_at = payload.scheduled_at
    for article in articles:
        article.status = "scheduled"
        submission = db.get(Submission, article.submission_id)
        if submission and submission.status == "production":
            submission.status = "scheduled"
            db.add(
                SubmissionWorkflowEvent(
                    submission_id=submission.id,
                    actor_id=operator_id(db, editor.id),
                    from_status="production",
                    to_status="scheduled",
                    reason=f"Scheduled for issue {issue.number}.",
                )
            )
    _audit(
        db,
        "publication.issue_scheduled",
        editor.id,
        "issue",
        issue.id,
        {"scheduled_at": issue.scheduled_at.isoformat()},
    )
    db.commit()
    return {
        "id": str(issue.id),
        "status": issue.status,
        "scheduled_at": issue.scheduled_at.isoformat(),
    }


def _issue_readiness(db: Session, issue: Issue, editor: User) -> list[dict]:
    articles = db.scalars(select(Article).where(Article.issue_id == issue.id)).all()
    if not articles:
        return [{"issue": str(issue.id), "blocker": "Issue has no assigned articles."}]
    blockers = []
    for article in articles:
        _active_editor_assignment(db, article.submission_id, editor.id)
        file_record = (
            db.get(SubmissionFile, article.final_file_id)
            if article.final_file_id
            else None
        )
        article_blockers = []
        if article.status not in {"production", "scheduled"}:
            article_blockers.append("Article is not in production or scheduled status.")
        if not article.title.strip() or not article.abstract.strip():
            article_blockers.append("Article title or abstract is missing.")
        if not db.scalar(
            select(ArticleAuthor.id).where(ArticleAuthor.article_id == article.id)
        ):
            article_blockers.append("Author metadata is missing.")
        if (
            file_record is None
            or file_record.submission_id != article.submission_id
            or file_record.scan_status != "clean"
        ):
            article_blockers.append("A clean final article file is missing.")
        if not article.license or not article.license_verified:
            article_blockers.append("Approved license details have not been verified.")
        if article.doi and not article.doi_verified:
            article_blockers.append("DOI registration has not been verified.")
        if article_blockers:
            blockers.append(
                {
                    "article_id": str(article.id),
                    "slug": article.slug,
                    "blockers": article_blockers,
                }
            )
    return blockers


@router.get("/api/v1/editorial/issues/{issue_id}/readiness")
def issue_readiness(
    issue_id: uuid.UUID, db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict:
    editor = _require_editor(actor)
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found.")
    blockers = _issue_readiness(db, issue, editor)
    return {"ready": not blockers, "blockers": blockers}


@router.post(
    "/api/v1/editorial/issues/{issue_id}/publish", dependencies=[Depends(require_csrf)]
)
def publish_issue(
    issue_id: uuid.UUID, db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict:
    editor = _require_editor(actor)
    issue = db.get(Issue, issue_id)
    if issue is None or issue.status not in {"draft", "scheduled"}:
        raise HTTPException(
            status_code=409, detail="Only draft or scheduled issues can be published."
        )
    if issue.scheduled_at:
        scheduled_at = (
            issue.scheduled_at
            if issue.scheduled_at.tzinfo
            else issue.scheduled_at.replace(tzinfo=UTC)
        )
        if scheduled_at > datetime.now(UTC):
            raise HTTPException(
                status_code=409, detail="The approved publication time has not arrived."
            )
    blockers = _issue_readiness(db, issue, editor)
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={"message": "Issue is not publication-ready.", "blockers": blockers},
        )
    articles = db.scalars(select(Article).where(Article.issue_id == issue.id)).all()
    now = datetime.now(UTC)
    for article in articles:
        article.status = "published"
        article.published_at = now
        db.add(
            ArticleHistory(
                article_id=article.id,
                actor_id=operator_id(db, editor.id),
                event_type="article_published",
                details={"issue_id": str(issue.id)},
            )
        )
        submission = db.get(Submission, article.submission_id)
        if submission and submission.status != "published":
            before = submission.status
            if before == "production":
                submission.status = "scheduled"
                db.add(
                    SubmissionWorkflowEvent(
                        submission_id=submission.id,
                        actor_id=operator_id(db, editor.id),
                        from_status="production",
                        to_status="scheduled",
                        reason=f"Published in issue {issue.number}.",
                    )
                )
                before = "scheduled"
            if before == "scheduled":
                submission.status = "published"
                db.add(
                    SubmissionWorkflowEvent(
                        submission_id=submission.id,
                        actor_id=operator_id(db, editor.id),
                        from_status="scheduled",
                        to_status="published",
                        reason=f"Published in issue {issue.number}.",
                    )
                )
    issue.status = "published"
    issue.published_at = now
    _audit(
        db,
        "publication.issue_published",
        editor.id,
        "issue",
        issue.id,
        {"article_count": len(articles)},
    )
    db.commit()
    return {
        "id": str(issue.id),
        "status": issue.status,
        "published_at": issue.published_at.isoformat(),
        "article_count": len(articles),
        "published_article_ids": [str(article.id) for article in articles],
    }


@router.post(
    "/api/v1/editorial/articles/{article_id}/scholarly-actions",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def record_scholarly_action(
    article_id: uuid.UUID,
    payload: ArticleActionInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    editor = _require_editor(actor)
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found.")
    _active_editor_assignment(db, article.submission_id, editor.id)
    if article.status == "published" and payload.action_type in {"withdrawal"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "Use a correction, expression of concern, or retraction for "
                "a published record."
            ),
        )
    if article.status != "published" and payload.action_type in {
        "correction",
        "expression_of_concern",
        "retraction",
    }:
        raise HTTPException(
            status_code=409, detail="This action applies to a published article."
        )
    record = ArticleScholarlyAction(
        article_id=article.id,
        actor_id=operator_id(db, editor.id),
        action_type=payload.action_type,
        statement=payload.statement,
        status="published" if payload.publish_public_notice else "draft",
        published_at=datetime.now(UTC) if payload.publish_public_notice else None,
    )
    db.add(record)
    if payload.action_type == "withdrawal" and article.status != "published":
        article.status = "withdrawn"
        submission = db.get(Submission, article.submission_id)
        if submission:
            before = submission.status
            submission.status = "withdrawn"
            db.add(
                SubmissionWorkflowEvent(
                    submission_id=submission.id,
                    actor_id=operator_id(db, editor.id),
                    from_status=before,
                    to_status="withdrawn",
                    reason=payload.statement,
                )
            )
    db.add(
        ArticleHistory(
            article_id=article.id,
            actor_id=operator_id(db, editor.id),
            event_type=payload.action_type,
            details={
                "action_id": str(record.id),
                "public": payload.publish_public_notice,
            },
        )
    )
    _audit(
        db,
        f"publication.{payload.action_type}",
        editor.id,
        "article",
        article.id,
        {"public": payload.publish_public_notice},
    )
    db.commit()
    return {"id": str(record.id), "status": record.status}


def _public_article_by_slug(db: Session, slug: str) -> Article | None:
    article = db.scalar(
        select(Article).where(Article.slug == slug, Article.status == "published")
    )
    if (
        article is None
        or article.issue_id is None
        or _issue_public(article.issue_id, db) is None
    ):
        return None
    return article


@router.get("/api/v1/public/issues")
def public_issues(db: DB) -> dict[str, list[dict]]:
    issues = db.scalars(
        select(Issue)
        .where(Issue.status == "published")
        .join(Volume, Volume.id == Issue.volume_id)
        .order_by(
            Volume.display_order,
            Issue.display_order,
            Volume.year.desc(),
            Volume.number.desc(),
            Issue.published_at.desc(),
        )
    ).all()
    items = []
    for issue in issues:
        if _issue_public(issue.id, db) is None:
            continue
        volume = db.get(Volume, issue.volume_id)
        articles = db.scalars(
            select(Article)
            .where(Article.issue_id == issue.id, Article.status == "published")
            .order_by(Article.title)
        ).all()
        items.append(
            {
                "id": str(issue.id),
                "number": issue.number,
                "title": issue.title,
                "description": issue.description,
                "published_at": issue.published_at.isoformat()
                if issue.published_at
                else None,
                "volume": {"number": volume.number, "year": volume.year}
                if volume
                else None,
                "articles": [
                    {
                        "slug": article.slug,
                        "title": article.title,
                        "url": f"/articles/{article.slug}",
                    }
                    for article in articles
                ],
            }
        )
    return {"items": items}


@router.get("/api/v1/public/issues/{issue_id}")
def public_issue_detail(issue_id: uuid.UUID, db: DB) -> dict:
    issue = _issue_public(issue_id, db)
    if issue is None:
        raise HTTPException(status_code=404, detail="Published issue not found.")
    volume = db.get(Volume, issue.volume_id)
    articles = db.scalars(
        select(Article)
        .where(Article.issue_id == issue.id, Article.status == "published")
        .order_by(Article.title)
    ).all()
    return {
        "id": str(issue.id),
        "number": issue.number,
        "title": issue.title,
        "description": issue.description,
        "published_at": issue.published_at.isoformat() if issue.published_at else None,
        "volume": {"number": volume.number, "year": volume.year} if volume else None,
        "articles": [_public_article_json(item, db) for item in articles],
    }


@router.get("/api/v1/public/articles/{slug}")
def public_article(slug: str, db: DB) -> dict:
    article = _public_article_by_slug(db, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Published article not found.")
    return _public_article_json(article, db)


@router.get("/api/v1/public/articles/{slug}/file")
def public_article_file(slug: str, db: DB) -> FileResponse:
    article = _public_article_by_slug(db, slug)
    if article is None or article.final_file_id is None:
        raise HTTPException(status_code=404, detail="Published article file not found.")
    retracted = db.scalar(
        select(ArticleScholarlyAction.id).where(
            ArticleScholarlyAction.article_id == article.id,
            ArticleScholarlyAction.action_type == "retraction",
            ArticleScholarlyAction.status == "published",
        )
    )
    if retracted:
        raise HTTPException(
            status_code=423,
            detail=(
                "The article file is unavailable following a published "
                "retraction notice."
            ),
        )
    file_record = db.get(SubmissionFile, article.final_file_id)
    if file_record is None or file_record.scan_status != "clean":
        raise HTTPException(status_code=423, detail="The article file is unavailable.")
    return FileResponse(
        safe_private_path(file_record.storage_name),
        media_type=file_record.media_type,
        filename=file_record.original_name,
    )


@router.get("/api/v1/public/research-areas")
def public_research_areas() -> dict:
    return {
        "items": [
            {"value": key, "label": label} for key, label in RESEARCH_AREAS.items()
        ]
    }


@router.get("/api/v1/public/search")
def public_search(
    db: DB, q: str = Query("", max_length=200), discipline: Discipline | None = None
) -> dict:
    query = " ".join(q.split())
    if len(query) < 2 and not discipline:
        return {"items": []}
    statement = (
        select(Article)
        .join(Issue, Article.issue_id == Issue.id)
        .where(
            Article.status == "published",
            Issue.status == "published",
            Article.published_at <= datetime.now(UTC),
        )
    )
    if discipline:
        statement = statement.where(Article.discipline == discipline)
    for term in query.split():
        escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        matching_ids = select(ArticleAuthor.article_id).where(
            ArticleAuthor.full_name.ilike(pattern, escape="\\")
        )
        statement = statement.where(
            or_(
                Article.title.ilike(pattern, escape="\\"),
                Article.abstract.ilike(pattern, escape="\\"),
                cast(Article.keywords, String).ilike(pattern, escape="\\"),
                Article.discipline.ilike(pattern, escape="\\"),
                Article.discipline_other.ilike(pattern, escape="\\"),
                Article.id.in_(matching_ids),
            )
        )
    articles = db.scalars(
        statement.order_by(Article.published_at.desc(), Article.id).limit(50)
    ).all()
    return {"items": [_public_article_json(article, db) for article in articles]}


@router.get("/api/v1/public/articles/{slug}/citation.ris")
def public_article_ris(slug: str, db: DB) -> Response:
    article = _public_article_by_slug(db, slug)
    if article is None:
        raise HTTPException(status_code=404, detail="Published article not found.")
    authors = db.scalars(
        select(ArticleAuthor)
        .where(ArticleAuthor.article_id == article.id)
        .order_by(ArticleAuthor.position)
    ).all()
    lines = ["TY  - JOUR", f"TI  - {article.title}"]
    lines.extend(f"AU  - {author.full_name}" for author in authors)
    if article.doi_verified and article.doi:
        lines.append(f"DO  - {article.doi}")
    if article.published_at:
        lines.append(f"PY  - {article.published_at.year}")
    lines.extend(["JO  - Noble Scientific Advances Journal", "ER  -", ""])
    return Response(
        "\r\n".join(lines),
        media_type="application/x-research-info-systems",
        headers={"Content-Disposition": f'attachment; filename="{article.slug}.ris"'},
    )
