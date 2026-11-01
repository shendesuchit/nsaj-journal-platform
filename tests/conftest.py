import os
from pathlib import Path

os.environ.update(
    APP_ENV="test",
    DB_PASSWORD="test",
    DATABASE_URL="sqlite+pysqlite:///:memory:",
    NSAJ_REQUIRE_PRIVILEGED_MFA="false",
)
import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.main import app
from app.models import Role, SubmissionChecklist, User
from app.services.security import hash_password

PASSWORD = "Testing-password-123!"


@pytest.fixture(autouse=True)
def database(tmp_path):
    settings = get_settings()
    settings.private_storage_path = tmp_path / "private"
    settings.mail_capture_path = (
        Path(__file__).resolve().parents[1] / ".local" / "test-mail"
    )
    settings.mail_backend = "capture"
    settings.email_intake_enabled = True
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())
    with get_session_factory()() as db:
        for role_name in ["author", "site_admin", "editor_in_chief"]:
            role = Role(name=role_name)
            db.add(
                User(
                    email=f"{role_name}@example.test",
                    display_name=role_name,
                    password_hash=hash_password(PASSWORD),
                    roles=[role],
                )
            )
        db.flush()
        chief = db.query(User).filter_by(email="editor_in_chief@example.test").one()
        from datetime import UTC, datetime

        db.add(
            SubmissionChecklist(
                title="Author declarations",
                declarations=["This is original work.", "All authors agree."],
                created_by_id=chief.id,
                approved_by_id=chief.id,
                approved_at=datetime.now(UTC),
            )
        )
        db.commit()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


@pytest.fixture
def session_factory(database):
    return get_session_factory()


def login(client, role="author"):
    client.cookies.clear()
    token = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    response = client.post(
        "/api/v1/auth/login",
        json={"email": f"{role}@example.test", "password": PASSWORD},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    client.headers["X-CSRF-Token"] = client.cookies.get("nsaj_csrf")
    return response
