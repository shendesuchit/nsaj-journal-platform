from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import get_authenticated_user, require_csrf
from app.db.session import get_db
from app.models import (
    Announcement,
    AuditEvent,
    CallForPapers,
    EditorialBoardProfile,
    PresentationResource,
    PublicPage,
    PublicPageHistory,
    PublicResourceFile,
    TemplateResource,
    User,
)
from app.services.content_schedule import effective_status
from app.services.private_files import safe_private_path, store_upload

router = APIRouter(tags=["public journal content"])
DB = Annotated[Session, Depends(get_db)]
MANAGEMENT_ROLES = {
    "site_admin",
    "editor_in_chief",
    "managing_editor",
    "associate_editor",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageInput(StrictModel):
    slug: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=50_000)


class CallInput(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=30_000)
    scope: str = Field(default="", max_length=10_000)
    manuscript_types: list[str] = Field(default_factory=list, max_length=10)
    instructions: str = Field(default="", max_length=10_000)
    related_issue_id: uuid.UUID | None = None
    opens_at: datetime | None = None
    deadline_at: datetime | None = None
    time_zone: str = Field(default="UTC", max_length=100)
    contact: str = Field(default="", max_length=320)
    display_order: int = Field(default=0, ge=0, le=10000)

    @field_validator("time_zone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Use a valid IANA time zone") from exc
        return value

    @field_validator("opens_at", "deadline_at")
    @classmethod
    def dates_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Dates must include a timezone")
        return value.astimezone(UTC)


class CallApprovalInput(StrictModel):
    status: Literal["open", "scheduled"]


class AnnouncementInput(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=20_000)
    publish_at: datetime | None = None

    @field_validator("publish_at")
    @classmethod
    def publish_date_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("publish_at must include a timezone")
        return value.astimezone(UTC)


class BoardInput(StrictModel):
    full_name: str = Field(min_length=1, max_length=200)
    role: Literal[
        "editor_in_chief", "associate_editor", "managing_editor", "board_member"
    ]
    qualifications: str = Field(default="", max_length=500)
    department: str = Field(default="", max_length=300)
    institution: str = Field(default="", max_length=300)
    country: str = Field(default="", max_length=100)
    specializations: list[str] = Field(default_factory=list, max_length=30)
    biography: str = Field(default="", max_length=5000)
    professional_url: str | None = Field(default=None, max_length=500)
    orcid: str | None = Field(default=None, max_length=19)
    professional_email: str | None = Field(default=None, max_length=320)
    appointment_start: datetime | None = None
    appointment_end: datetime | None = None
    display_order: int = Field(default=0, ge=0, le=10000)

    @field_validator("appointment_start", "appointment_end")
    @classmethod
    def appointment_dates_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Appointment dates must include a timezone")
        return value.astimezone(UTC)


class BoardVerificationInput(StrictModel):
    identity_verified: bool
    qualification_verified: bool
    affiliation_verified: bool
    appointment_confirmed: bool
    consent_status: Literal["pending", "granted", "withdrawn"]
    consent_evidence_reference: str = Field(default="", max_length=500)
    public_fields: list[str] = Field(default_factory=list, max_length=20)


class BoardPublishInput(StrictModel):
    public_approved: bool


class PresentationInput(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    presenter: str = Field(default="", max_length=300)
    resource_type: str = Field(min_length=1, max_length=100)
    summary: str = Field(default="", max_length=10_000)
    occurred_at: datetime | None = None
    external_url: str | None = Field(default=None, max_length=1000)
    file_id: uuid.UUID | None = None
    related_article_id: uuid.UUID | None = None
    related_issue_id: uuid.UUID | None = None
    display_order: int = Field(default=0, ge=0, le=10000)

    @field_validator("occurred_at")
    @classmethod
    def occurrence_must_be_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("occurred_at must include a timezone")
        return value.astimezone(UTC) if value else None


def _manager(user: User) -> User:
    if not ({role.name for role in user.roles} & MANAGEMENT_ROLES):
        raise HTTPException(
            status_code=403, detail="A journal content management role is required."
        )
    return user


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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
            actor_id=actor_id,
            event_type=event,
            target_type=target_type,
            target_id=str(target_id),
            details=details or {},
        )
    )


def _page_slug(value: str) -> str:
    slug = value.strip().lower().replace(" ", "-")
    if not slug.replace("-", "").isalnum():
        raise HTTPException(
            status_code=422, detail="Page slug must use letters, numbers, and hyphens."
        )
    return slug


@router.get("/api/v1/admin/pages")
def admin_pages(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    _manager(actor)
    pages = db.scalars(select(PublicPage).order_by(PublicPage.slug)).all()
    return {
        "items": [
            {
                "id": str(item.id),
                "slug": item.slug,
                "title": item.title,
                "status": item.status,
                "version": item.version,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in pages
        ]
    }


@router.post(
    "/api/v1/admin/pages", status_code=201, dependencies=[Depends(require_csrf)]
)
def create_page(
    payload: PageInput, db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict:
    manager = _manager(actor)
    slug = _page_slug(payload.slug)
    if db.scalar(select(PublicPage.id).where(PublicPage.slug == slug)) is not None:
        raise HTTPException(
            status_code=409, detail="A page already exists for this slug."
        )
    page = PublicPage(
        slug=slug,
        title=payload.title,
        body=payload.body,
        status="draft",
        version=1,
        updated_by_id=manager.id,
    )
    db.add(page)
    db.flush()
    db.add(
        PublicPageHistory(
            page_id=page.id,
            version=page.version,
            title=page.title,
            body=page.body,
            status=page.status,
            actor_id=manager.id,
        )
    )
    _audit(db, "content.page_created", manager.id, "public_page", page.id)
    db.commit()
    return {
        "id": str(page.id),
        "slug": page.slug,
        "version": page.version,
        "status": page.status,
    }


@router.put("/api/v1/admin/pages/{slug}", dependencies=[Depends(require_csrf)])
def update_page(
    slug: str,
    payload: PageInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    page = db.scalar(select(PublicPage).where(PublicPage.slug == _page_slug(slug)))
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    if _page_slug(payload.slug) != page.slug:
        raise HTTPException(
            status_code=422, detail="Page slug is stable after creation."
        )
    db.add(
        PublicPageHistory(
            page_id=page.id,
            version=page.version,
            title=page.title,
            body=page.body,
            status=page.status,
            actor_id=manager.id,
        )
    )
    page.version += 1
    page.title = payload.title
    page.body = payload.body
    page.status = "draft"
    page.approved_by_id = None
    page.published_at = None
    page.updated_by_id = manager.id
    db.add(
        PublicPageHistory(
            page_id=page.id,
            version=page.version,
            title=page.title,
            body=page.body,
            status=page.status,
            actor_id=manager.id,
        )
    )
    _audit(
        db,
        "content.page_updated",
        manager.id,
        "public_page",
        page.id,
        {"version": page.version},
    )
    db.commit()
    return {
        "id": str(page.id),
        "slug": page.slug,
        "version": page.version,
        "status": page.status,
    }


@router.post("/api/v1/admin/pages/{slug}/publish", dependencies=[Depends(require_csrf)])
def publish_page(
    slug: str, db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict:
    manager = _manager(actor)
    page = db.scalar(select(PublicPage).where(PublicPage.slug == _page_slug(slug)))
    if page is None:
        raise HTTPException(status_code=404, detail="Page not found.")
    page.status = "published"
    page.approved_by_id = manager.id
    page.published_at = datetime.now(UTC)
    db.add(
        PublicPageHistory(
            page_id=page.id,
            version=page.version,
            title=page.title,
            body=page.body,
            status="published",
            actor_id=manager.id,
        )
    )
    _audit(
        db,
        "content.page_published",
        manager.id,
        "public_page",
        page.id,
        {"version": page.version},
    )
    db.commit()
    return {"slug": page.slug, "status": page.status, "version": page.version}


@router.get("/api/v1/public/pages/{slug}")
def public_page(slug: str, db: DB) -> dict:
    page = db.scalar(select(PublicPage).where(PublicPage.slug == _page_slug(slug)))
    if page is None:
        raise HTTPException(status_code=404, detail="Published page not found.")
    if page.status == "published":
        return {
            "slug": page.slug,
            "title": page.title,
            "body": page.body,
            "published_at": page.published_at.isoformat()
            if page.published_at
            else None,
        }
    previous = db.scalar(
        select(PublicPageHistory)
        .where(
            PublicPageHistory.page_id == page.id,
            PublicPageHistory.status == "published",
        )
        .order_by(PublicPageHistory.version.desc(), PublicPageHistory.created_at.desc())
    )
    if previous is None:
        raise HTTPException(status_code=404, detail="Published page not found.")
    return {
        "slug": page.slug,
        "title": previous.title,
        "body": previous.body,
        "published_at": previous.created_at.isoformat(),
    }


def _record(db, model, item_id, version=None):
    item = db.scalar(select(model).where(model.id == item_id).with_for_update())
    if item is None:
        raise HTTPException(404, "Content not found.")
    if version is not None and item.version != version:
        raise HTTPException(409, "This item has changed. Refresh before editing.")
    return item


def _content_json(item):
    names = (
        [
            "title",
            "description",
            "scope",
            "manuscript_types",
            "instructions",
            "related_issue_id",
            "opens_at",
            "deadline_at",
            "time_zone",
            "contact",
            "display_order",
        ]
        if isinstance(item, CallForPapers)
        else ["title", "body", "publish_at", "published_at"]
    )
    data = {key: getattr(item, key) for key in names}
    for key, value in data.items():
        if isinstance(value, datetime):
            data[key] = _utc(value).isoformat()
        if isinstance(value, uuid.UUID):
            data[key] = str(value)
    data.update(id=str(item.id), status=effective_status(item), version=item.version)
    if (
        isinstance(item, Announcement)
        and data["status"] == "published"
        and not data["published_at"]
    ):
        data["published_at"] = data["publish_at"]
    return data


def _validate_call(payload):
    if (
        payload.opens_at
        and payload.deadline_at
        and payload.deadline_at <= payload.opens_at
    ):
        raise HTTPException(422, "The deadline must be later than the opening time.")


@router.get("/api/v1/admin/calls-for-papers")
def admin_calls(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict:
    _manager(actor)
    return {
        "items": [
            _content_json(row)
            for row in db.scalars(
                select(CallForPapers).order_by(CallForPapers.created_at.desc())
            )
        ]
    }


@router.post(
    "/api/v1/admin/calls-for-papers",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_call(
    payload: CallInput, db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict:
    manager = _manager(actor)
    _validate_call(payload)
    item = CallForPapers(
        **payload.model_dump(), status="draft", created_by_id=manager.id
    )
    db.add(item)
    db.flush()
    _audit(db, "content.call_created", manager.id, "call", item.id)
    db.commit()
    return _content_json(item)


@router.patch(
    "/api/v1/admin/calls-for-papers/{item_id}", dependencies=[Depends(require_csrf)]
)
def edit_call(
    item_id: uuid.UUID,
    payload: CallInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int = Query(ge=1),
) -> dict:
    manager = _manager(actor)
    item = _record(db, CallForPapers, item_id, version)
    if effective_status(item) not in {"draft", "scheduled"}:
        raise HTTPException(
            409, "Only drafts and future scheduled items can be edited."
        )
    _validate_call(payload)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.status = "draft"
    item.approved_by_id = None
    item.approved_at = None
    item.version += 1
    _audit(db, "content.call_updated", manager.id, "call", item.id)
    db.commit()
    return _content_json(item)


@router.delete(
    "/api/v1/admin/calls-for-papers/{item_id}", dependencies=[Depends(require_csrf)]
)
def delete_call(
    item_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int = Query(ge=1),
) -> dict:
    manager = _manager(actor)
    item = _record(db, CallForPapers, item_id, version)
    if effective_status(item) not in {"draft", "scheduled"}:
        raise HTTPException(409, "Archive published items instead of deleting them.")
    _audit(
        db, "content.call_deleted", manager.id, "call", item.id, {"title": item.title}
    )
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post(
    "/api/v1/admin/calls-for-papers/{item_id}/cancel-schedule",
    dependencies=[Depends(require_csrf)],
)
def cancel_schedule_call(
    item_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int = Query(ge=1),
) -> dict:
    manager = _manager(actor)
    item = _record(db, CallForPapers, item_id, version)
    if effective_status(item) != "scheduled":
        raise HTTPException(409, "Only future scheduled items can be cancelled.")
    item.approved_by_id = None
    item.status = "draft"
    item.version += 1
    _audit(db, "content.call_cancel-schedule", manager.id, "call", item.id)
    db.commit()
    return _content_json(item)


@router.post(
    "/api/v1/admin/calls-for-papers/{item_id}/archive",
    dependencies=[Depends(require_csrf)],
)
def archive_call(
    item_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int = Query(ge=1),
) -> dict:
    manager = _manager(actor)
    item = _record(db, CallForPapers, item_id, version)
    item.status = "archived"
    item.version += 1
    _audit(db, "content.call_archive", manager.id, "call", item.id)
    db.commit()
    return _content_json(item)


@router.post(
    "/api/v1/admin/calls-for-papers/{item_id}/close",
    dependencies=[Depends(require_csrf)],
)
def close_call(
    item_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int = Query(ge=1),
) -> dict:
    manager = _manager(actor)
    item = _record(db, CallForPapers, item_id, version)
    if effective_status(item) not in {"open", "scheduled"}:
        raise HTTPException(409, "Only open or scheduled calls can be closed.")
    item.status = "closed"
    item.version += 1
    _audit(db, "content.call_close", manager.id, "call", item.id)
    db.commit()
    return _content_json(item)


@router.get("/api/v1/admin/announcements")
def admin_announcements(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict:
    _manager(actor)
    return {
        "items": [
            _content_json(row)
            for row in db.scalars(
                select(Announcement).order_by(Announcement.created_at.desc())
            )
        ]
    }


@router.post(
    "/api/v1/admin/announcements", status_code=201, dependencies=[Depends(require_csrf)]
)
def create_announcement(
    payload: AnnouncementInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    item = Announcement(
        **payload.model_dump(), status="draft", created_by_id=manager.id
    )
    db.add(item)
    db.flush()
    _audit(db, "content.announcement_created", manager.id, "announcement", item.id)
    db.commit()
    return _content_json(item)


@router.patch(
    "/api/v1/admin/announcements/{item_id}", dependencies=[Depends(require_csrf)]
)
def edit_announcement(
    item_id: uuid.UUID,
    payload: AnnouncementInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int = Query(ge=1),
) -> dict:
    manager = _manager(actor)
    item = _record(db, Announcement, item_id, version)
    if effective_status(item) not in {"draft", "scheduled"}:
        raise HTTPException(
            409, "Only drafts and future scheduled items can be edited."
        )
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.status = "draft"
    item.approved_by_id = None
    item.version += 1
    _audit(db, "content.announcement_updated", manager.id, "announcement", item.id)
    db.commit()
    return _content_json(item)


@router.delete(
    "/api/v1/admin/announcements/{item_id}", dependencies=[Depends(require_csrf)]
)
def delete_announcement(
    item_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int = Query(ge=1),
) -> dict:
    manager = _manager(actor)
    item = _record(db, Announcement, item_id, version)
    if effective_status(item) not in {"draft", "scheduled"}:
        raise HTTPException(409, "Archive published items instead of deleting them.")
    _audit(
        db,
        "content.announcement_deleted",
        manager.id,
        "announcement",
        item.id,
        {"title": item.title},
    )
    db.delete(item)
    db.commit()
    return {"ok": True}


@router.post(
    "/api/v1/admin/announcements/{item_id}/cancel-schedule",
    dependencies=[Depends(require_csrf)],
)
def cancel_schedule_announcement(
    item_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int = Query(ge=1),
) -> dict:
    manager = _manager(actor)
    item = _record(db, Announcement, item_id, version)
    if effective_status(item) != "scheduled":
        raise HTTPException(409, "Only future scheduled items can be cancelled.")
    item.approved_by_id = None
    item.status = "draft"
    item.version += 1
    _audit(
        db, "content.announcement_cancel-schedule", manager.id, "announcement", item.id
    )
    db.commit()
    return _content_json(item)


@router.post(
    "/api/v1/admin/announcements/{item_id}/archive",
    dependencies=[Depends(require_csrf)],
)
def archive_announcement(
    item_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int = Query(ge=1),
) -> dict:
    manager = _manager(actor)
    item = _record(db, Announcement, item_id, version)
    item.status = "archived"
    item.version += 1
    _audit(db, "content.announcement_archive", manager.id, "announcement", item.id)
    db.commit()
    return _content_json(item)


@router.post(
    "/api/v1/admin/calls-for-papers/{item_id}/approve",
    dependencies=[Depends(require_csrf)],
)
def approve_call(
    item_id: uuid.UUID,
    payload: CallApprovalInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int | None = None,
) -> dict:
    manager = _manager(actor)
    item = _record(db, CallForPapers, item_id, version)
    if item.status != "draft":
        raise HTTPException(409, "Only drafts can be approved.")
    now = datetime.now(UTC)
    if item.deadline_at and _utc(item.deadline_at) <= now:
        raise HTTPException(422, "The deadline must be in the future.")
    future = bool(item.opens_at and _utc(item.opens_at) > now)
    if (payload.status == "scheduled") != future:
        raise HTTPException(
            422,
            "Choose scheduled for a future opening, or open for immediate publication.",
        )
    item.status = payload.status
    item.approved_by_id = manager.id
    item.approved_at = now
    item.version += 1
    _audit(db, "content.call_approved", manager.id, "call", item.id)
    db.commit()
    return _content_json(item)


def _approve_announcement(db, item_id, actor, version, scheduled):
    manager = _manager(actor)
    item = _record(db, Announcement, item_id, version)
    if item.status not in {"draft", "scheduled"}:
        raise HTTPException(409, "Only unpublished announcements can be approved.")
    now = datetime.now(UTC)
    future = bool(item.publish_at and _utc(item.publish_at) > now)
    if future != scheduled:
        raise HTTPException(
            422, "Use schedule for a future time, or publish for immediate publication."
        )
    item.status = "scheduled" if scheduled else "published"
    item.published_at = None if scheduled else now
    item.approved_by_id = manager.id
    item.version += 1
    _audit(
        db,
        "content.announcement_approved",
        manager.id,
        "announcement",
        item.id,
        {"status": item.status},
    )
    db.commit()
    return _content_json(item)


@router.post(
    "/api/v1/admin/announcements/{item_id}/schedule",
    dependencies=[Depends(require_csrf)],
)
def schedule_announcement(
    item_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int = Query(ge=1),
) -> dict:
    return _approve_announcement(db, item_id, actor, version, True)


@router.post(
    "/api/v1/admin/announcements/{item_id}/publish",
    dependencies=[Depends(require_csrf)],
)
def publish_announcement(
    item_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    version: int | None = None,
) -> dict:
    return _approve_announcement(db, item_id, actor, version, False)


@router.get("/api/v1/public/calls-for-papers")
def public_calls(db: DB) -> dict:
    rows = db.scalars(
        select(CallForPapers)
        .where(CallForPapers.approved_at.is_not(None))
        .order_by(CallForPapers.display_order, CallForPapers.deadline_at)
    ).all()
    return {
        "items": [
            _content_json(row)
            for row in rows
            if effective_status(row) in {"open", "closed"}
            and (not row.opens_at or _utc(row.opens_at) <= datetime.now(UTC))
        ]
    }


@router.get("/api/v1/public/announcements")
def public_announcements(db: DB) -> dict:
    rows = db.scalars(
        select(Announcement).where(Announcement.status.in_(["published", "scheduled"]))
    ).all()
    items = [_content_json(row) for row in rows if effective_status(row) == "published"]
    return {
        "items": sorted(items, key=lambda row: row["published_at"] or "", reverse=True)
    }


@router.get("/api/v1/admin/templates")
def admin_templates(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    _manager(actor)
    rows = db.execute(
        select(TemplateResource, PublicResourceFile.scan_status)
        .join(PublicResourceFile, TemplateResource.file_id == PublicResourceFile.id)
        .order_by(TemplateResource.created_at.desc(), TemplateResource.title)
    ).all()
    return {
        "items": [
            {
                "id": str(resource.id),
                "title": resource.title,
                "category": resource.category,
                "status": resource.status,
                "scan_status": scan_status,
            }
            for resource, scan_status in rows
        ]
    }


@router.post(
    "/api/v1/admin/templates", status_code=201, dependencies=[Depends(require_csrf)]
)
async def create_template(
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
    upload: Annotated[UploadFile, File()],
    title: str = Form(min_length=1, max_length=300),
    category: str = Form(min_length=1, max_length=100),
    description: str = Form(default="", max_length=10_000),
    language: str = Form(default="", max_length=50),
    version: str = Form(min_length=1, max_length=50),
) -> dict:
    manager = _manager(actor)
    stored = await store_upload(upload)
    public_file = PublicResourceFile(
        storage_name=stored.storage_name,
        original_name=stored.original_name,
        media_type=stored.media_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        scan_status=stored.scan_status,
        created_by_id=manager.id,
    )
    db.add(public_file)
    db.flush()
    resource = TemplateResource(
        title=title,
        category=category,
        description=description,
        language=language,
        version=version,
        file_id=public_file.id,
        status="draft",
        created_by_id=manager.id,
    )
    db.add(resource)
    _audit(
        db,
        "content.template_uploaded",
        manager.id,
        "template",
        resource.id,
        {"scan_status": stored.scan_status},
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        stored.path.unlink(missing_ok=True)
        raise
    return {
        "id": str(resource.id),
        "status": resource.status,
        "scan_status": public_file.scan_status,
    }


@router.post(
    "/api/v1/admin/resources", status_code=201, dependencies=[Depends(require_csrf)]
)
async def create_public_resource_file(
    upload: UploadFile,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    stored = await store_upload(upload)
    resource_file = PublicResourceFile(
        storage_name=stored.storage_name,
        original_name=stored.original_name,
        media_type=stored.media_type,
        size_bytes=stored.size_bytes,
        sha256=stored.sha256,
        scan_status=stored.scan_status,
        created_by_id=manager.id,
    )
    db.add(resource_file)
    _audit(
        db,
        "content.resource_file_uploaded",
        manager.id,
        "public_resource_file",
        resource_file.id,
        {"scan_status": stored.scan_status},
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        stored.path.unlink(missing_ok=True)
        raise
    return {"id": str(resource_file.id), "scan_status": resource_file.scan_status}


@router.post(
    "/api/v1/admin/templates/{template_id}/publish",
    dependencies=[Depends(require_csrf)],
)
def publish_template(
    template_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    resource = db.get(TemplateResource, template_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    file_record = db.get(PublicResourceFile, resource.file_id)
    if file_record is None or file_record.scan_status != "clean":
        raise HTTPException(
            status_code=423,
            detail="The template cannot be published until scanning succeeds.",
        )
    previous = db.scalars(
        select(TemplateResource).where(
            TemplateResource.title == resource.title,
            TemplateResource.category == resource.category,
            TemplateResource.status == "published",
            TemplateResource.id != resource.id,
        )
    ).all()
    for item in previous:
        item.status = "inactive"
    resource.status = "published"
    resource.approved_by_id = manager.id
    resource.published_at = datetime.now(UTC)
    _audit(db, "content.template_published", manager.id, "template", resource.id)
    db.commit()
    return {"id": str(resource.id), "status": resource.status}


@router.post(
    "/api/v1/admin/templates/{template_id}/deactivate",
    dependencies=[Depends(require_csrf)],
)
def deactivate_template(
    template_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    resource = db.get(TemplateResource, template_id)
    if resource is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    resource.status = "inactive"
    _audit(db, "content.template_deactivated", manager.id, "template", resource.id)
    db.commit()
    return {"id": str(resource.id), "status": resource.status}


@router.get("/api/v1/public/templates")
def public_templates(db: DB) -> dict[str, list[dict]]:
    rows = db.scalars(
        select(TemplateResource)
        .where(TemplateResource.status == "published")
        .order_by(TemplateResource.display_order, TemplateResource.title)
    ).all()
    items = []
    for row in rows:
        file_record = db.get(PublicResourceFile, row.file_id)
        if file_record and file_record.scan_status == "clean":
            items.append(
                {
                    "id": str(row.id),
                    "title": row.title,
                    "category": row.category,
                    "description": row.description,
                    "language": row.language,
                    "version": row.version,
                    "effective_at": row.effective_at.isoformat()
                    if row.effective_at
                    else None,
                    "file_type": file_record.media_type,
                    "download_url": f"/api/v1/public/templates/{row.id}/file",
                }
            )
    return {"items": items}


@router.get("/api/v1/public/templates/{template_id}/file")
def download_public_template(template_id: uuid.UUID, db: DB) -> FileResponse:
    resource = db.get(TemplateResource, template_id)
    if resource is None or resource.status != "published":
        raise HTTPException(status_code=404, detail="Published template not found.")
    file_record = db.get(PublicResourceFile, resource.file_id)
    if file_record is None or file_record.scan_status != "clean":
        raise HTTPException(status_code=423, detail="Template file is unavailable.")
    return FileResponse(
        safe_private_path(file_record.storage_name),
        media_type=file_record.media_type,
        filename=file_record.original_name,
    )


@router.get("/api/v1/admin/board")
def admin_board(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    _manager(actor)
    rows = db.scalars(
        select(EditorialBoardProfile).order_by(
            EditorialBoardProfile.display_order, EditorialBoardProfile.full_name
        )
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "full_name": row.full_name,
                "role": row.role,
                "institution": row.institution,
                "is_active": row.is_active,
                "identity_verified": row.identity_verified,
                "qualification_verified": row.qualification_verified,
                "affiliation_verified": row.affiliation_verified,
                "appointment_confirmed": row.appointment_confirmed,
                "consent_status": row.consent_status,
                "public_approved": row.public_approved,
            }
            for row in rows
        ]
    }


@router.post(
    "/api/v1/admin/board", status_code=201, dependencies=[Depends(require_csrf)]
)
def create_board_profile(
    payload: BoardInput, db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict:
    manager = _manager(actor)
    profile = EditorialBoardProfile(**payload.model_dump(), updated_by_id=manager.id)
    db.add(profile)
    _audit(db, "board.profile_created", manager.id, "board_profile", profile.id)
    db.commit()
    return {"id": str(profile.id), "public_approved": profile.public_approved}


@router.put("/api/v1/admin/board/{profile_id}", dependencies=[Depends(require_csrf)])
def update_board_profile(
    profile_id: uuid.UUID,
    payload: BoardInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    profile = db.get(EditorialBoardProfile, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=404, detail="Editorial board profile not found."
        )
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    profile.public_approved = False
    profile.consent_status = "pending"
    profile.updated_by_id = manager.id
    _audit(db, "board.profile_updated", manager.id, "board_profile", profile.id)
    db.commit()
    return {
        "id": str(profile.id),
        "public_approved": profile.public_approved,
        "consent_status": profile.consent_status,
    }


@router.post(
    "/api/v1/admin/board/{profile_id}/verification",
    dependencies=[Depends(require_csrf)],
)
def verify_board_profile(
    profile_id: uuid.UUID,
    payload: BoardVerificationInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    profile = db.get(EditorialBoardProfile, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=404, detail="Editorial board profile not found."
        )
    profile.identity_verified = payload.identity_verified
    profile.qualification_verified = payload.qualification_verified
    profile.affiliation_verified = payload.affiliation_verified
    profile.appointment_confirmed = payload.appointment_confirmed
    profile.consent_status = payload.consent_status
    profile.consent_evidence_reference = payload.consent_evidence_reference or None
    profile.consented_public_fields = (
        payload.public_fields if payload.consent_status == "granted" else []
    )
    profile.verified_by_id = manager.id
    profile.verified_at = datetime.now(UTC)
    profile.public_approved = False
    _audit(
        db,
        "board.verification_updated",
        manager.id,
        "board_profile",
        profile.id,
        {"consent_status": profile.consent_status},
    )
    db.commit()
    return {
        "id": str(profile.id),
        "public_approved": profile.public_approved,
        "consent_status": profile.consent_status,
    }


@router.post(
    "/api/v1/admin/board/{profile_id}/publish", dependencies=[Depends(require_csrf)]
)
def publish_board_profile(
    profile_id: uuid.UUID,
    payload: BoardPublishInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    profile = db.get(EditorialBoardProfile, profile_id)
    if profile is None:
        raise HTTPException(
            status_code=404, detail="Editorial board profile not found."
        )
    required_fields = {"full_name", "role"}
    if payload.public_approved and not (
        profile.is_active
        and profile.identity_verified
        and profile.qualification_verified
        and profile.affiliation_verified
        and profile.appointment_confirmed
        and profile.consent_status == "granted"
        and profile.consent_evidence_reference
        and required_fields.issubset(set(profile.consented_public_fields))
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Verification, appointment, and field-specific consent are "
                "required before publication."
            ),
        )
    profile.public_approved = payload.public_approved
    _audit(
        db,
        "board.profile_publication_changed",
        manager.id,
        "board_profile",
        profile.id,
        {"public_approved": profile.public_approved},
    )
    db.commit()
    return {"id": str(profile.id), "public_approved": profile.public_approved}


@router.get("/api/v1/public/editorial-board")
def public_editorial_board(db: DB) -> dict[str, list[dict]]:
    now = datetime.now(UTC)
    rows = db.scalars(
        select(EditorialBoardProfile)
        .where(
            EditorialBoardProfile.is_active.is_(True),
            EditorialBoardProfile.public_approved.is_(True),
            EditorialBoardProfile.identity_verified.is_(True),
            EditorialBoardProfile.qualification_verified.is_(True),
            EditorialBoardProfile.affiliation_verified.is_(True),
            EditorialBoardProfile.appointment_confirmed.is_(True),
            EditorialBoardProfile.consent_status == "granted",
        )
        .order_by(EditorialBoardProfile.display_order)
    ).all()
    items = []
    for row in rows:
        if row.appointment_start and _utc(row.appointment_start) > now:
            continue
        if row.appointment_end and _utc(row.appointment_end) < now:
            continue
        allowed = set(row.consented_public_fields)
        public_fields = {"id": str(row.id)}
        candidate = {
            "full_name": row.full_name,
            "role": row.role,
            "qualifications": row.qualifications,
            "department": row.department,
            "institution": row.institution,
            "country": row.country,
            "specializations": row.specializations,
            "biography": row.biography,
            "professional_url": row.professional_url,
            "orcid": row.orcid,
            "professional_email": row.professional_email,
        }
        public_fields.update(
            {key: value for key, value in candidate.items() if key in allowed and value}
        )
        items.append(public_fields)
    return {"items": items}


@router.get("/api/v1/admin/presentations")
def admin_presentations(
    db: DB, actor: Annotated[User, Depends(get_authenticated_user)]
) -> dict[str, list[dict]]:
    _manager(actor)
    rows = db.execute(
        select(PresentationResource, PublicResourceFile.scan_status)
        .outerjoin(
            PublicResourceFile, PresentationResource.file_id == PublicResourceFile.id
        )
        .order_by(PresentationResource.created_at.desc(), PresentationResource.title)
    ).all()
    return {
        "items": [
            {
                "id": str(resource.id),
                "title": resource.title,
                "resource_type": resource.resource_type,
                "status": resource.status,
                "occurred_at": resource.occurred_at.isoformat()
                if resource.occurred_at
                else None,
                "has_external_url": bool(resource.external_url),
                "scan_status": scan_status,
            }
            for resource, scan_status in rows
        ]
    }


@router.post(
    "/api/v1/admin/presentations", status_code=201, dependencies=[Depends(require_csrf)]
)
def create_presentation(
    payload: PresentationInput,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    if payload.external_url and not payload.external_url.startswith("https://"):
        raise HTTPException(
            status_code=422, detail="External resource links must use HTTPS."
        )
    if payload.file_id:
        file_record = db.get(PublicResourceFile, payload.file_id)
        if file_record is None:
            raise HTTPException(
                status_code=422, detail="Select an uploaded public resource file."
            )
    item = PresentationResource(
        **payload.model_dump(),
        status="draft",
        access_status="public",
        created_by_id=manager.id,
    )
    db.add(item)
    _audit(db, "content.presentation_created", manager.id, "presentation", item.id)
    db.commit()
    return {"id": str(item.id), "status": item.status}


@router.post(
    "/api/v1/admin/presentations/{resource_id}/publish",
    dependencies=[Depends(require_csrf)],
)
def publish_presentation(
    resource_id: uuid.UUID,
    db: DB,
    actor: Annotated[User, Depends(get_authenticated_user)],
) -> dict:
    manager = _manager(actor)
    item = db.get(PresentationResource, resource_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Presentation resource not found.")
    if not item.file_id and not item.external_url:
        raise HTTPException(
            status_code=409,
            detail="A resource file or approved HTTPS link is required.",
        )
    if item.file_id:
        file_record = db.get(PublicResourceFile, item.file_id)
        if file_record is None or file_record.scan_status != "clean":
            raise HTTPException(
                status_code=423,
                detail="The resource file is unavailable until it passes scanning.",
            )
    item.status = "published"
    item.approved_by_id = manager.id
    item.published_at = datetime.now(UTC)
    _audit(db, "content.presentation_published", manager.id, "presentation", item.id)
    db.commit()
    return {"id": str(item.id), "status": item.status}


@router.get("/api/v1/public/presentations")
def public_presentations(db: DB) -> dict[str, list[dict]]:
    items = db.scalars(
        select(PresentationResource)
        .where(
            PresentationResource.status == "published",
            PresentationResource.access_status == "public",
        )
        .order_by(
            PresentationResource.display_order, PresentationResource.occurred_at.desc()
        )
    ).all()
    result = []
    for item in items:
        file_record = db.get(PublicResourceFile, item.file_id) if item.file_id else None
        if item.file_id and (file_record is None or file_record.scan_status != "clean"):
            continue
        result.append(
            {
                "id": str(item.id),
                "title": item.title,
                "presenter": item.presenter,
                "resource_type": item.resource_type,
                "summary": item.summary,
                "occurred_at": item.occurred_at.isoformat()
                if item.occurred_at
                else None,
                "external_url": item.external_url,
                "file_url": f"/api/v1/public/presentations/{item.id}/file"
                if item.file_id
                else None,
            }
        )
    return {"items": result}


@router.get("/api/v1/public/presentations/{resource_id}/file")
def download_presentation_file(resource_id: uuid.UUID, db: DB) -> FileResponse:
    item = db.get(PresentationResource, resource_id)
    if (
        item is None
        or item.status != "published"
        or item.access_status != "public"
        or item.file_id is None
    ):
        raise HTTPException(
            status_code=404, detail="Published resource file not found."
        )
    file_record = db.get(PublicResourceFile, item.file_id)
    if file_record is None or file_record.scan_status != "clean":
        raise HTTPException(status_code=423, detail="Resource file is unavailable.")
    return FileResponse(
        safe_private_path(file_record.storage_name),
        media_type=file_record.media_type,
        filename=file_record.original_name,
    )
