import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from urllib.parse import parse_qs, urlparse

import pytest
from conftest import login
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import (
    Announcement,
    Article,
    ArticleAuthor,
    CallForPapers,
    EmailIntake,
    Issue,
    OutboundMail,
    Submission,
    SubmissionReceipt,
    User,
    Volume,
)
from app.services.content_schedule import publish_due
from app.services.email_intake import ingest_message
from app.services.mail_delivery import dispatch_pending, queue_message
from app.services.research_areas import RESEARCH_AREAS

PDF = b"%PDF-1.7\nTest manuscript\n%%EOF"


def details(area="clinical"):
    return dict(
        title="Clinical research study",
        abstract="Research abstract",
        keywords=["study"],
        manuscript_type="original research",
        discipline=area,
        discipline_other="History of science" if area == "other" else None,
        authors=[
            dict(
                full_name="Ada Smith",
                affiliation="Research Institute",
                email="author@example.test",
            )
        ],
    )


def submit(client, draft):
    policy = client.get("/api/v1/author/submission-checklist").json()["checklist"]
    return client.post(
        f"/api/v1/author/submissions/{draft}/submit",
        json={"checklist_id": policy["id"], "acknowledged_indices": [0, 1]},
    )


@pytest.mark.parametrize("area", list(RESEARCH_AREAS))
def test_all_areas_formal_submission(client, area):
    login(client)
    response = client.post("/api/v1/author/submissions", json=details(area))
    assert response.status_code == 201, response.text
    draft = response.json()["id"]
    response = client.post(
        f"/api/v1/author/submissions/{draft}/files",
        files={"upload": ("paper.pdf", PDF, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    response = submit(client, draft)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "submitted"
    with get_session_factory()() as db:
        receipt = db.scalar(
            select(SubmissionReceipt).where(
                SubmissionReceipt.submission_id == uuid.UUID(draft)
            )
        )
        assert receipt.manuscript_snapshot["discipline"] == area
        assert (
            receipt.manuscript_snapshot["discipline_other"]
            == details(area)["discipline_other"]
        )


def test_missing_area_and_legacy_patch(client):
    login(client)
    data = details()
    data.pop("discipline")
    data.pop("discipline_other")
    draft = client.post("/api/v1/author/submissions", json=data).json()["id"]
    response = submit(client, draft)
    assert response.status_code == 422 and "area of research" in response.text
    client.patch(f"/api/v1/author/submissions/{draft}", json=details("genetics"))
    assert (
        client.patch(f"/api/v1/author/submissions/{draft}", json=data).json()[
            "discipline"
        ]
        == "genetics"
    )
    data = details("other")
    data["discipline_other"] = "   "
    client.patch(f"/api/v1/author/submissions/{draft}", json=data)
    assert "other area of research" in submit(client, draft).text
    assert (
        client.post(
            "/api/v1/author/submissions", json={**data, "discipline": "not-valid"}
        ).status_code
        == 422
    )


def seed_articles():
    with get_session_factory()() as db:
        user = db.scalar(select(User).where(User.email == "author@example.test"))
        volume = Volume(number=1, year=2026, created_by_id=user.id)
        db.add(volume)
        db.flush()
        issue = Issue(
            volume_id=volume.id, number="1", status="published", created_by_id=user.id
        )
        hidden = Issue(
            volume_id=volume.id, number="2", status="draft", created_by_id=user.id
        )
        db.add_all([issue, hidden])
        db.flush()
        for index in range(57):
            sub = Submission(
                reference=f"NSAJ-{10000000 + index}",
                submitting_author_id=user.id,
                title="paper",
                status="published",
            )
            db.add(sub)
            db.flush()
            article = Article(
                submission_id=sub.id,
                issue_id=hidden.id if index >= 3 else issue.id,
                slug=f"paper-{index}",
                title=[
                    "Clinical outcomes",
                    "Materials at 100% efficiency",
                    "Unrelated systems",
                ][index % 3],
                abstract="An abstract",
                keywords=[],
                discipline="clinical" if index == 0 else "materials",
                status="published",
                published_at=datetime.now(UTC) - timedelta(minutes=60 - index),
                created_by_id=user.id,
            )
            db.add(article)
            db.flush()
            db.add(
                ArticleAuthor(
                    article_id=article.id,
                    position=0,
                    full_name="Ada Smith" if index != 2 else "John Doe",
                    affiliation="Institute",
                )
            )
        db.commit()


def test_search_author_title_visibility_and_literals(client):
    seed_articles()

    def search(q="", **kwargs):
        response = client.get("/api/v1/public/search", params={"q": q, **kwargs})
        assert response.status_code == 200, response.text
        return response.json()["items"]

    assert {x["slug"] for x in search("ADA")} == {"paper-0", "paper-1"}
    assert [x["slug"] for x in search("Smith clinical")] == ["paper-0"]
    assert [x["slug"] for x in search("outcomes")] == ["paper-0"]
    assert [x["slug"] for x in search("100%")] == ["paper-1"]
    assert search("%%") == []
    assert [x["slug"] for x in search(discipline="clinical")] == ["paper-0"]
    assert search("missing person") == []
    assert (
        client.get("/api/v1/public/search", params={"q": "a" * 201}).status_code == 422
    )


@pytest.mark.parametrize("kind", ["announcements", "calls-for-papers"])
def test_scheduled_content_lifecycle(client, kind):
    login(client, "site_admin")
    future = (datetime.now(UTC) + timedelta(days=2)).isoformat()
    payload = {
        "title": "Future announcement",
        **(
            {"body": "Announcement body", "publish_at": future}
            if kind == "announcements"
            else {
                "description": "Call description",
                "opens_at": future,
                "deadline_at": (datetime.now(UTC) + timedelta(days=5)).isoformat(),
            }
        ),
    }
    base = "/api/v1/admin/" + kind
    item = client.post(base, json=payload).json()
    assert item["status"] == "draft"
    path = f"{base}/{item['id']}"

    def approve(item):
        action = "schedule" if kind == "announcements" else "approve"
        response = client.post(
            f"{path}/{action}?version={item['version']}",
            json={} if kind == "announcements" else {"status": "scheduled"},
        )
        assert response.status_code == 200, response.text
        return response.json()

    item = approve(item)
    assert item["status"] == "scheduled"
    stored = client.get(base).json()["items"][0]
    assert stored["publish_at" if kind == "announcements" else "opens_at"].endswith(
        "+00:00"
    )
    assert client.get("/api/v1/public/" + kind).json()["items"] == []
    assert client.patch(path + "?version=1", json=payload).status_code == 409
    item = client.patch(
        path + f"?version={item['version']}", json={**payload, "title": "Rescheduled"}
    ).json()
    assert item["status"] == "draft"
    item = approve(item)
    item = client.post(path + f"/cancel-schedule?version={item['version']}").json()
    assert item["status"] == "draft"
    item = approve(item)
    assert client.delete(path + f"?version={item['version']}").status_code == 200
    item = client.post(base, json=payload).json()
    path = f"{base}/{item['id']}"
    item = approve(item)
    with get_session_factory()() as db:
        row = db.get(
            Announcement if kind == "announcements" else CallForPapers,
            uuid.UUID(item["id"]),
        )
        if kind == "announcements":
            row.publish_at = datetime.now(UTC) - timedelta(minutes=1)
        else:
            row.opens_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    assert (
        len(client.get("/api/v1/public/" + kind).json()["items"]) == 1
    )  # reads reflect time before worker tick
    with get_session_factory()() as db:
        publish_due(db)
    item = client.get(base).json()["items"][0]
    assert item["status"] == ("published" if kind == "announcements" else "open")
    assert client.delete(path + f"?version={item['version']}").status_code == 409
    assert client.post(path + f"/archive?version={item['version']}").status_code == 200
    assert client.get("/api/v1/public/" + kind).json()["items"] == []
    login(client)
    assert client.post(base, json=payload).status_code == 403


def email(sender="author@example.test", message_id="<paper@example.test>"):
    message = EmailMessage()
    message["From"] = f"Ada Smith <{sender}>"
    message["To"] = "submit@example.test"
    message["Subject"] = "New research"
    message["Message-ID"] = message_id
    message.set_content(
        "Title: Clinical email research\nArea of research: Clinical Science\n"
        "Manuscript type: original research\nAbstract: Research abstract\n"
        "Keywords: clinical, study\nAffiliation: Institute"
    )
    message.add_attachment(
        PDF, maintype="application", subtype="pdf", filename="paper.pdf"
    )
    return message.as_bytes()


def ingest(raw):
    with get_session_factory()() as db:
        return asyncio.run(ingest_message(raw, db))


def latest_link():
    paths = list(get_settings().mail_capture_path.glob("*.json"))
    return json.loads(max(paths, key=lambda p: p.stat().st_mtime_ns).read_text())[
        "link"
    ]


def test_email_claim_duplicate_owner_expiry_and_submission(client):
    raw = email()
    row, created = ingest(raw)
    assert created
    again, created = ingest(raw)
    assert not created and row.id == again.id
    token = parse_qs(urlparse(latest_link()).fragment)["token"][0]
    login(client, "site_admin")
    assert (
        client.post(
            "/api/v1/author/email-intake/claim", json={"token": token}
        ).status_code
        == 403
    )
    login(client)
    assert (
        client.post(
            "/api/v1/author/email-intake/claim", json={"token": "x" * 32}
        ).status_code
        == 404
    )
    response = client.post("/api/v1/author/email-intake/claim", json={"token": token})
    assert response.status_code == 200, response.text
    draft = response.json()["id"]
    assert (
        client.post("/api/v1/author/email-intake/claim", json={"token": token}).json()[
            "id"
        ]
        == draft
    )
    data = client.get("/api/v1/author/submissions/" + draft).json()
    assert (
        data["discipline"] == "clinical"
        and len(data["files"]) == 1
        and data["status"] == "draft"
    )
    assert submit(client, draft).status_code == 200
    row, _ = ingest(email(message_id="<expired@example.test>"))
    token = parse_qs(urlparse(latest_link()).fragment)["token"][0]
    with get_session_factory()() as db:
        item = db.get(EmailIntake, row.id)
        item.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert (
        client.post(
            "/api/v1/author/email-intake/claim", json={"token": token}
        ).status_code
        == 410
    )


def test_email_new_author_invitation(client):
    ingest(email("new-author@example.test"))
    tokens = parse_qs(urlparse(latest_link()).fragment)
    client.get("/api/v1/auth/csrf")
    client.headers["X-CSRF-Token"] = client.cookies.get("nsaj_csrf")
    response = client.post(
        "/api/v1/invitations/accept",
        json={"token": tokens["token"][0], "password": "Testing-new-password-123!"},
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies.get("nsaj_csrf")
    assert response.json()["role"] == "author"
    response = client.post(
        "/api/v1/author/email-intake/claim", json={"token": tokens["intake"][0]}
    )
    assert response.status_code == 200, response.text
    assert submit(client, response.json()["id"]).status_code == 200


def test_email_invalid_attachments_and_sender(client):
    message = EmailMessage()
    message["From"] = "author@example.test"
    message["Subject"] = "A paper"
    message.set_content("Abstract: Example")
    message.add_attachment(
        b"not a PDF", maintype="application", subtype="pdf", filename="paper.pdf"
    )
    row, _ = ingest(message.as_bytes())
    assert row.files == [] and row.warnings
    message["Auto-Submitted"] = "auto-generated"
    with pytest.raises(ValueError, match="Automated"):
        ingest(message.as_bytes())


def test_mail_encryption_and_retry(monkeypatch):
    from cryptography.fernet import Fernet
    from pydantic import SecretStr

    settings = get_settings()
    settings.mail_backend = "smtp"
    settings.smtp_host = "smtp.example.test"
    settings.smtp_from = "journal@example.test"
    settings.mail_encryption_key = SecretStr(Fernet.generate_key().decode())
    sent = []

    class FakeSMTP:
        fail = True

        def __init__(self, *args, **kwargs):
            pass

        def starttls(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def send_message(self, message):
            if self.fail:
                raise OSError("Temporary failure")
            sent.append(message)

    monkeypatch.setattr("app.services.mail_delivery.smtplib.SMTP", FakeSMTP)
    with get_session_factory()() as db:
        queue_message(
            db,
            recipient="author@example.test",
            subject="Test",
            link="https://example.test/#token=secret",
        )
        db.commit()
        row = db.scalar(select(OutboundMail))
        assert "secret" not in row.payload and row.encrypted
        dispatch_pending(db)
        assert row.attempts == 1 and row.status == "pending"
        row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        FakeSMTP.fail = False
        dispatch_pending(db)
        assert row.status == "sent" and row.payload == "" and len(sent) == 1


def test_imap_marks_only_committed_messages(monkeypatch):
    from pydantic import SecretStr

    from app.services.email_intake import poll_mailbox

    settings = get_settings()
    settings.imap_host = "imap.example.test"
    settings.imap_username = "intake"
    settings.imap_password = SecretStr("test-only")
    settings.submission_email = "submit@example.test"
    raw = email(message_id="<imap@example.test>")
    flags = []

    class FakeIMAP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def login(self, *args):
            pass

        def select(self, *args):
            return "OK", []

        def uid(self, action, *args):
            if action == "search":
                return "OK", [b"1"]
            if action == "fetch":
                if args[1] == "(RFC822.SIZE)":
                    return "OK", [f"1 (RFC822.SIZE {len(raw)})".encode()]
                assert args[1] == "(BODY.PEEK[])"
                return "OK", [(b"1", raw)]
            if action == "store":
                with get_session_factory()() as db:
                    assert db.scalar(select(EmailIntake)) is not None
                flags.append(args[-1])
                return "OK", []

    monkeypatch.setattr("app.services.email_intake.imaplib.IMAP4_SSL", FakeIMAP)
    with get_session_factory()() as db:
        poll_mailbox(db)
    assert flags == ["(\\Seen)"]
    flags.clear()

    def fail(*args, **kwargs):
        raise RuntimeError("Mail provider unavailable")

    monkeypatch.setattr("app.services.email_intake.queue_message", fail)
    raw = email(message_id="<retry@example.test>")
    with get_session_factory()() as db:
        with pytest.raises(RuntimeError):
            poll_mailbox(db)
        assert len(db.scalars(select(EmailIntake)).all()) == 1
    assert flags == []


def test_new_migration_preserves_legacy_data(tmp_path):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect, text

    # Recreate only the affected legacy columns; older migrations target PostgreSQL.
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    source = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/d94e21a7b630_research_content_email.py"
    )
    spec = importlib.util.spec_from_file_location("migration_under_test", source)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        for table in ["submissions", "articles", "announcements", "calls_for_papers"]:
            connection.execute(
                text(
                    f"CREATE TABLE {table} (id VARCHAR(32) PRIMARY KEY, "
                    "title TEXT, discipline VARCHAR(30))"
                )
            )
            connection.execute(
                text(f"INSERT INTO {table} VALUES ('old', 'Existing item', 'science')")
            )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.execute(
            text("SELECT title, discipline, discipline_other FROM submissions")
        ).one() == ("Existing item", "science", None)
        assert (
            connection.execute(text("SELECT version FROM announcements")).scalar() == 1
        )
        assert "email_intakes" in inspect(connection).get_table_names()
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert connection.execute(
            text("SELECT title, discipline FROM submissions")
        ).one() == ("Existing item", "science")
        assert "email_intakes" not in inspect(connection).get_table_names()


def test_email_wrong_author_and_csrf(client):
    from app.models import Role
    from app.services.security import hash_password

    ingest(email())
    token = parse_qs(urlparse(latest_link()).fragment)["token"][0]
    with get_session_factory()() as db:
        role = db.scalar(select(Role).where(Role.name == "author"))
        db.add(
            User(
                email="other@example.test",
                display_name="Other",
                password_hash=hash_password("Testing-password-123!"),
                roles=[role],
            )
        )
        db.commit()
    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    client.post(
        "/api/v1/auth/login",
        json={"email": "other@example.test", "password": "Testing-password-123!"},
        headers={"X-CSRF-Token": csrf},
    )
    response = client.post("/api/v1/author/email-intake/claim", json={"token": token})
    assert response.status_code == 403
    client.headers["X-CSRF-Token"] = client.cookies.get("nsaj_csrf")
    response = client.post("/api/v1/author/email-intake/claim", json={"token": token})
    assert response.status_code == 404
