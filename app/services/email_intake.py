import asyncio
import hashlib
import imaplib
import io
import re
import secrets
import ssl
from datetime import UTC, datetime, timedelta
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses

from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import AuditEvent, EmailIntake, Invitation, Role, User
from app.services.mail_delivery import delivery_configured, queue_message, valid_address
from app.services.private_files import store_upload
from app.services.research_areas import RESEARCH_AREAS
from app.services.security import hash_secret


def intake_available():
    s = get_settings()
    return bool(
        s.email_intake_enabled
        and delivery_configured()
        and valid_address(s.submission_email)
        and s.imap_host
        and s.imap_username
        and s.imap_password
    )


def parse_fields(body):
    fields = {}
    current = None
    for line in body.splitlines():
        match = re.match(
            r"^(Title|Paper title|Abstract|Keywords|Affiliation|Area of research|"
            r"Other area|Manuscript type):\s*(.*)",
            line,
            re.I,
        )
        if match:
            current = match[1].lower()
            fields[current] = match[2].strip()
        elif current == "abstract":
            fields[current] += "\n" + line
    area = fields.get("area of research", "").casefold()
    discipline = next(
        (
            key
            for key, label in RESEARCH_AREAS.items()
            if area in {key, label.casefold()}
        ),
        None,
    )
    manuscript_type = fields.get("manuscript type", "").lower()
    return dict(
        abstract=fields.get("abstract", "").strip()[:50000],
        keywords=[
            x.strip() for x in fields.get("keywords", "").split(",") if x.strip()
        ][:30],
        affiliation=fields.get("affiliation", "")[:500],
        discipline=discipline,
        discipline_other=fields.get("other area", "")[:200]
        if discipline == "other"
        else None,
        manuscript_type=manuscript_type
        if manuscript_type
        in {"original research", "review article", "case study", "technical paper"}
        else None,
        title=fields.get("title", fields.get("paper title", ""))[:500],
    )


async def ingest_message(raw, db):
    s = get_settings()
    if not s.email_intake_enabled or not delivery_configured():
        raise RuntimeError("Email intake is not configured")
    if len(raw) > s.max_intake_message_bytes:
        raise ValueError("Message exceeds intake size limit")
    message = BytesParser(policy=policy.default).parsebytes(raw)
    if message.get("Auto-Submitted", "no").lower() != "no":
        raise ValueError("Automated message ignored")
    addresses = getaddresses(message.get_all("From", []))
    if len(addresses) != 1:
        raise ValueError("Exactly one sender is required")
    name, sender = addresses[0]
    sender = sender.strip().casefold()
    if not valid_address(sender) or sender == s.submission_email.casefold():
        raise ValueError("Invalid sender")
    digest = hashlib.sha256(raw).hexdigest()
    key = hashlib.sha256(
        (sender + "\n" + str(message.get("Message-ID", digest))).encode()
    ).hexdigest()
    existing = db.scalar(select(EmailIntake).where(EmailIntake.message_key == key))
    if existing:
        if existing.message_hash != digest:
            raise ValueError("Message-ID reused for different content")
        return existing, False
    count = db.scalar(
        select(func.count())
        .select_from(EmailIntake)
        .where(
            EmailIntake.sender_email == sender,
            EmailIntake.received_at >= datetime.now(UTC) - timedelta(days=1),
        )
    )
    if count >= 5:
        raise ValueError("Daily sender intake limit reached")
    parts = list(message.walk())
    attachments = [part for part in parts if part.get_filename()]
    if len(parts) > 100 or len(attachments) > 10:
        raise ValueError("Too many message parts or attachments")
    body = message.get_body(preferencelist=("plain",))
    metadata = parse_fields(body.get_content() if body else "")
    title = (
        metadata.pop("title")
        or re.sub(
            r"^(re:|fw:|fwd:)\s*",
            "",
            str(message.get("Subject", "Emailed manuscript")),
            flags=re.I,
        )[:500]
    )
    token = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=s.email_intake_lifetime_hours)
    row = EmailIntake(
        message_key=key,
        message_hash=digest,
        sender_email=sender,
        sender_name=(name or sender.split("@")[0])[:200],
        title=title,
        metadata_fields=metadata,
        token_hash=hash_secret(token),
        expires_at=expires,
    )
    stored_files = []
    warnings = []
    created_paths = []
    try:
        db.add(row)
        db.flush()
        for part in attachments:
            try:
                stored = await store_upload(
                    UploadFile(
                        file=io.BytesIO(part.get_payload(decode=True) or b""),
                        filename=part.get_filename(),
                    )
                )
                created_paths.append(stored.path)
                stored_files.append(
                    {
                        key: getattr(stored, key)
                        for key in (
                            "storage_name",
                            "original_name",
                            "media_type",
                            "size_bytes",
                            "sha256",
                            "scan_status",
                        )
                    }
                )
                if stored.scan_status != "clean":
                    warnings.append(
                        f"{stored.original_name}: scanning did not pass; "
                        "upload a clean file in your workspace."
                    )
            except HTTPException as exc:
                warnings.append(f"{part.get_filename()}: {exc.detail}")
        if not stored_files:
            warnings.append(
                "No usable manuscript attachment was received. "
                "Upload a PDF or DOCX in your workspace."
            )
        row.files, row.warnings = stored_files, warnings
        user = db.scalar(select(User).where(func.lower(User.email) == sender))
        link = s.public_base_url.rstrip("/") + "/email-submission#token=" + token
        if user is None:
            role = db.scalar(select(Role).where(Role.name == "author"))
            if role is None:
                role = Role(name="author")
                db.add(role)
                db.flush()
            invitation_token = secrets.token_urlsafe(32)
            db.add(
                Invitation(
                    email=sender,
                    display_name=row.sender_name,
                    role_id=role.id,
                    token_hash=hash_secret(invitation_token),
                    expires_at=expires,
                )
            )
            link = (
                s.public_base_url.rstrip("/")
                + "/accept-invitation#token="
                + invitation_token
                + "&intake="
                + token
            )
        queue_message(
            db,
            recipient=sender,
            subject="NSAJ manuscript received — confirm your draft",
            link=link,
            body=(
                "Your email has been received, but your paper is not formally "
                "submitted. Sign in or accept your author invitation, review the "
                "imported draft, and confirm all declarations. This link expires "
                f"in {s.email_intake_lifetime_hours} hours."
            ),
        )
        db.add(
            AuditEvent(
                event_type="submission.email_received",
                target_type="email_intake",
                target_id=str(row.id),
                details={"attachments": len(stored_files)},
            )
        )
        db.commit()
        return row, True
    except Exception:
        db.rollback()
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise


def poll_mailbox(db):
    s = get_settings()
    if not intake_available():
        return
    with imaplib.IMAP4_SSL(
        s.imap_host, s.imap_port, ssl_context=ssl.create_default_context(), timeout=30
    ) as mailbox:
        mailbox.login(s.imap_username, s.imap_password.get_secret_value())
        status, _ = mailbox.select(s.imap_folder)
        if status != "OK":
            raise RuntimeError("Cannot select intake mailbox")
        status, data = mailbox.uid("search", None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("Cannot search intake mailbox")
        for uid in data[0].split()[:20]:
            try:
                status, sizes = mailbox.uid("fetch", uid, "(RFC822.SIZE)")
                if status != "OK":
                    raise RuntimeError("Cannot inspect email")
                size = re.search(
                    rb"RFC822.SIZE (\d+)",
                    b" ".join(x for x in sizes if isinstance(x, bytes)),
                )
                if not size:
                    raise RuntimeError("Missing email size")
                if int(size[1]) > s.max_intake_message_bytes:
                    raise ValueError("Message exceeds intake size limit")
                status, data = mailbox.uid("fetch", uid, "(BODY.PEEK[])")
                if status != "OK":
                    raise RuntimeError("Cannot fetch email")
                raw = next(item[1] for item in data if isinstance(item, tuple))
                asyncio.run(ingest_message(raw, db))
                mailbox.uid("store", uid, "+FLAGS", "(\\Seen)")
            except ValueError as exc:
                db.rollback()
                db.add(
                    AuditEvent(
                        event_type="submission.email_rejected",
                        target_type="email_intake",
                        details={"reason": str(exc)},
                    )
                )
                db.commit()
                mailbox.uid("store", uid, "+FLAGS", "(\\Seen \\Flagged)")
            except Exception:
                db.rollback()
                raise
