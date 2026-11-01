from datetime import UTC, datetime

from sqlalchemy import select

from app.models import Announcement, AuditEvent, CallForPapers


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def effective_status(item, now=None):
    now = now or datetime.now(UTC)
    if isinstance(item, Announcement):
        if (
            item.status == "scheduled"
            and item.approved_by_id
            and item.publish_at
            and utc(item.publish_at) <= now
        ):
            return "published"
    elif item.status in {"scheduled", "open"} and item.approved_at:
        if item.opens_at and utc(item.opens_at) > now:
            return "scheduled"
        if item.deadline_at and utc(item.deadline_at) <= now:
            return "closed"
        return "open"
    return item.status


def publish_due(db):
    for model in (Announcement, CallForPapers):
        for item in db.scalars(
            select(model)
            .where(model.status.in_(["scheduled", "open"]))
            .with_for_update(skip_locked=True)
        ):
            status = effective_status(item)
            if status != item.status:
                item.status = status
                item.version += 1
                if isinstance(item, Announcement):
                    item.published_at = item.publish_at
                db.add(
                    AuditEvent(
                        event_type="content.schedule_executed",
                        target_type=item.__tablename__,
                        target_id=str(item.id),
                        details={"status": status},
                    )
                )
    db.commit()
