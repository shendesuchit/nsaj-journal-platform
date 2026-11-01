import json
import re
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import get_settings
from app.models import OutboundMail
from app.services.mail import capture_local_message


def valid_address(value):
    return bool(re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", value))


def delivery_configured():
    s = get_settings()
    if s.mail_backend == "capture":
        return s.app_env.casefold() in {"development", "test"}
    if not s.smtp_host or not valid_address(s.smtp_from):
        return False
    if s.smtp_username and not s.smtp_password:
        return False
    if s.app_env.casefold() not in {"development", "test"} and (
        not s.mail_encryption_key or not s.public_base_url.startswith("https://")
    ):
        return False
    if s.mail_encryption_key:
        try:
            Fernet(s.mail_encryption_key.get_secret_value().encode())
        except ValueError:
            return False
    return True


def require_delivery():
    if not delivery_configured():
        raise HTTPException(503, "Email delivery is not configured.")


def queue_message(db, *, recipient, subject, link, body=""):
    require_delivery()
    s = get_settings()
    if s.mail_backend == "capture":
        capture_local_message(recipient=recipient, subject=subject, link=link)
        return
    payload = json.dumps({"link": link, "body": body})
    if s.mail_encryption_key:
        payload = (
            Fernet(s.mail_encryption_key.get_secret_value().encode())
            .encrypt(payload.encode())
            .decode()
        )
    db.add(
        OutboundMail(
            recipient=recipient,
            subject=subject,
            payload=payload,
            encrypted=bool(s.mail_encryption_key),
        )
    )


def dispatch_pending(db):
    s = get_settings()
    if s.mail_backend != "smtp" or not delivery_configured():
        return
    rows = db.scalars(
        select(OutboundMail)
        .where(
            OutboundMail.status == "pending",
            OutboundMail.next_attempt_at <= datetime.now(UTC),
        )
        .order_by(OutboundMail.created_at)
        .limit(10)
        .with_for_update(skip_locked=True)
    ).all()
    for row in rows:
        try:
            content = row.payload
            if row.encrypted:
                content = (
                    Fernet(s.mail_encryption_key.get_secret_value().encode())
                    .decrypt(content.encode())
                    .decode()
                )
            content = json.loads(content)
            message = EmailMessage()
            message["From"], message["To"], message["Subject"] = (
                s.smtp_from,
                row.recipient,
                row.subject,
            )
            message["Message-ID"] = f"<{row.id}@{s.smtp_from.split('@')[1]}>"
            message["Auto-Submitted"] = "auto-generated"
            message.set_content(content["body"] + "\n\n" + content["link"])
            context = ssl.create_default_context()
            if s.smtp_security == "ssl":
                transport = smtplib.SMTP_SSL(
                    s.smtp_host, s.smtp_port, timeout=30, context=context
                )
            else:
                transport = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=30)
                transport.starttls(context=context)
            with transport:
                if s.smtp_username:
                    transport.login(s.smtp_username, s.smtp_password.get_secret_value())
                transport.send_message(message)
            row.status, row.sent_at, row.payload, row.last_error = (
                "sent",
                datetime.now(UTC),
                "",
                None,
            )
        except Exception as exc:
            row.attempts += 1
            row.last_error = type(exc).__name__
            row.status = "failed" if row.attempts >= 5 else "pending"
            row.next_attempt_at = datetime.now(UTC) + timedelta(
                minutes=min(30, 2**row.attempts)
            )
    db.commit()
