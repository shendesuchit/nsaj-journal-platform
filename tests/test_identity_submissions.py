from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.testclient import TestClient

from app.api.auth import CSRF_COOKIE
from app.core.config import get_settings
from app.models import (
    AuthSession,
    Invitation,
    MfaRecoveryCode,
    Role,
    Submission,
    SubmissionFile,
    User,
    UserMfa,
)
from app.services.security import (
    encrypt_totp_secret,
    hash_password,
    hash_secret,
    new_one_time_secret,
    new_recovery_codes,
    new_totp_secret,
    totp_code,
)

PASSWORD = "correct horse battery staple 2026"


def create_user(
    factory: sessionmaker[Session],
    email: str,
    role_name: str,
    *,
    password: str = PASSWORD,
    mfa: bool = False,
) -> tuple[uuid.UUID, str | None, list[str]]:
    with factory() as db:
        role = db.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            role = Role(name=role_name)
            db.add(role)
            db.flush()
        user = User(
            email=email,
            display_name=email.split("@", 1)[0],
            password_hash=hash_password(password),
            roles=[role],
        )
        secret = new_totp_secret() if mfa else None
        recovery_codes = new_recovery_codes() if mfa else []
        if secret is not None:
            user.mfa = UserMfa(
                encrypted_totp_secret=encrypt_totp_secret(secret),
                enabled=True,
                recovery_codes=[
                    MfaRecoveryCode(code_hash=hash_secret(code))
                    for code in recovery_codes
                ],
            )
        db.add(user)
        db.commit()
        return user.id, secret, recovery_codes


def csrf(client: TestClient) -> str:
    return client.get("/api/v1/auth/csrf").json()["csrf_token"]


def login(client: TestClient, email: str, password: str = PASSWORD) -> dict:
    token = csrf(client)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200, response.text
    return response.json()


def login_admin(client: TestClient, email: str, secret: str) -> str:
    result = login(client, email)
    assert result["mfa_required"] is True
    token = result["csrf_token"]
    response = client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": totp_code(secret)},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    return token


def test_invitation_is_hashed_expires_and_is_single_use(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    admin_id, secret, _ = create_user(
        session_factory, "admin@example.test", "site_admin", mfa=True
    )
    token = login_admin(client, "admin@example.test", secret or "")
    response = client.post(
        "/api/v1/invitations",
        json={
            "email": "author@example.test",
            "display_name": "Author Example",
            "role": "author",
        },
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    assert "token" not in response.text.lower()

    with session_factory() as db:
        invitation = db.scalar(
            select(Invitation).where(Invitation.email == "author@example.test")
        )
        assert invitation is not None
        message_path = next(get_settings().mail_capture_path.resolve().glob("*.json"))
        message = json.loads(message_path.read_text(encoding="utf-8"))
        raw_token = message["link"].split("#token=", maxsplit=1)[1]
        assert invitation.token_hash == hash_secret(raw_token)
        assert raw_token not in invitation.token_hash

    csrf(client)
    accepted = client.post(
        "/api/v1/invitations/accept",
        json={"token": raw_token, "password": PASSWORD},
        headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
    )
    assert accepted.status_code == 200
    user_id = accepted.json()
    assert user_id["ok"] is True
    assert user_id["mfa_setup"] is None

    csrf(client)
    replay = client.post(
        "/api/v1/invitations/accept",
        json={"token": raw_token, "password": PASSWORD},
        headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
    )
    assert replay.status_code == 400

    with session_factory() as db:
        expired_role = db.scalar(select(Role).where(Role.name == "author"))
        expired = new_one_time_secret()
        db.add(
            Invitation(
                email="expired@example.test",
                display_name="Expired",
                role_id=expired_role.id,
                token_hash=hash_secret(expired),
                invited_by_id=admin_id,
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        db.commit()
    csrf(client)
    expired_response = client.post(
        "/api/v1/invitations/accept",
        json={"token": expired, "password": PASSWORD},
        headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
    )
    assert expired_response.status_code == 400


def test_mfa_and_one_use_recovery_code(client: TestClient, session_factory) -> None:
    _, secret, codes = create_user(
        session_factory, "editor@example.test", "editor_in_chief", mfa=True
    )
    result = login(client, "editor@example.test")
    assert result["mfa_required"] is True
    csrf_token = result["csrf_token"]
    denied = client.get("/api/v1/author/submissions")
    assert denied.status_code == 403
    assert (
        client.post(
            "/api/v1/auth/mfa/verify",
            json={"code": totp_code(secret or "")},
            headers={"X-CSRF-Token": csrf_token},
        ).status_code
        == 200
    )

    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token})
    result = login(client, "editor@example.test")
    recovered = client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": codes[0]},
        headers={"X-CSRF-Token": result["csrf_token"]},
    )
    assert recovered.status_code == 200
    client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": result["csrf_token"]})
    result = login(client, "editor@example.test")
    replay = client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": codes[0]},
        headers={"X-CSRF-Token": result["csrf_token"]},
    )
    assert replay.status_code == 401


def test_csrf_login_throttle_and_password_recovery_revoke_sessions(
    client: TestClient, session_factory
) -> None:
    create_user(session_factory, "throttle@example.test", "author")
    create_user(session_factory, "recovery@example.test", "author")
    bad = client.post(
        "/api/v1/auth/login",
        json={"email": "throttle@example.test", "password": "wrong"},
    )
    assert bad.status_code == 403
    token = csrf(client)
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "throttle@example.test", "password": "wrong"},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 401
    throttled = client.post(
        "/api/v1/auth/login",
        json={"email": "throttle@example.test", "password": PASSWORD},
        headers={"X-CSRF-Token": token},
    )
    assert throttled.status_code == 429

    login(client, "recovery@example.test")
    old_session = client.cookies.get("nsaj_session")
    recovery_csrf = csrf(client)
    requested = client.post(
        "/api/v1/auth/recovery/request",
        json={"email": "recovery@example.test"},
        headers={"X-CSRF-Token": recovery_csrf},
    )
    assert requested.status_code == 200
    mail_path = next(get_settings().mail_capture_path.resolve().glob("*.json"))
    mail = json.loads(mail_path.read_text(encoding="utf-8"))
    reset_token = mail["link"].split("#token=", maxsplit=1)[1]
    recovery = client.post(
        "/api/v1/auth/recovery/complete",
        json={"token": reset_token, "password": "new secure password 2026"},
        headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
    )
    assert recovery.status_code == 200
    stale_client = TestClient(client.app, raise_server_exceptions=False)
    stale_client.cookies.set("nsaj_session", old_session)
    assert stale_client.get("/api/v1/auth/me").status_code == 401
    stale_client.close()
    csrf(client)
    replay = client.post(
        "/api/v1/auth/recovery/complete",
        json={"token": reset_token, "password": "another secure password 2026"},
        headers={"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)},
    )
    assert replay.status_code == 400
    assert login(client, "recovery@example.test", "new secure password 2026")[
        "authenticated"
    ]


def test_draft_ownership_upload_validation_and_scan_blocking(
    client: TestClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id, _, _ = create_user(session_factory, "owner@example.test", "author")
    other_id, _, _ = create_user(session_factory, "other@example.test", "author")
    owner = login(client, "owner@example.test")
    csrf_token = owner["csrf_token"]
    payload = {
        "title": "Confidential study",
        "abstract": "Working draft",
        "keywords": ["science"],
        "manuscript_type": "original research",
        "authors": [
            {"full_name": "Lead Author", "affiliation": "Institute A", "email": None},
            {"full_name": "Coauthor", "affiliation": "Institute B", "email": None},
        ],
    }
    created = client.post(
        "/api/v1/author/submissions",
        json=payload,
        headers={"X-CSRF-Token": csrf_token},
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["status"] == "draft"
    assert [item["full_name"] for item in draft["authors"]] == [
        "Lead Author",
        "Coauthor",
    ]
    assert "submit" not in draft

    invalid_extension = client.post(
        f"/api/v1/author/submissions/{draft['id']}/files",
        files={"upload": ("payload.exe", b"MZ", "application/octet-stream")},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert invalid_extension.status_code == 415

    settings = get_settings()
    settings.max_upload_bytes = 16
    oversized = client.post(
        f"/api/v1/author/submissions/{draft['id']}/files",
        files={"upload": ("large.pdf", b"A" * 17, "application/pdf")},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert oversized.status_code == 413
    settings.max_upload_bytes = 50 * 1024 * 1024

    import app.services.private_files as file_service

    monkeypatch.setattr(file_service, "scan_with_defender", lambda _: "unavailable")
    pdf = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
    uploaded = client.post(
        f"/api/v1/author/submissions/{draft['id']}/files",
        files={"upload": ("manuscript.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert uploaded.status_code == 201
    file_data = uploaded.json()
    assert file_data["scan_status"] == "unavailable"
    assert file_data["download_available"] is False
    blocked = client.get(
        f"/api/v1/author/submissions/{draft['id']}/files/{file_data['id']}"
    )
    assert blocked.status_code == 423

    monkeypatch.setattr(file_service, "scan_with_defender", lambda _: "failed")
    failed_scan = client.post(
        f"/api/v1/author/submissions/{draft['id']}/files",
        files={"upload": ("failed-scan.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert failed_scan.status_code == 201
    assert failed_scan.json()["scan_status"] == "failed"
    denied_download = client.get(
        f"/api/v1/author/submissions/{draft['id']}/files/{failed_scan.json()['id']}"
    )
    assert denied_download.status_code == 423

    other_client = TestClient(client.app, raise_server_exceptions=False)
    login(other_client, "other@example.test")
    foreign = other_client.get(f"/api/v1/author/submissions/{draft['id']}")
    assert foreign.status_code == 404
    foreign_download = other_client.get(
        f"/api/v1/author/submissions/{draft['id']}/files/{file_data['id']}"
    )
    assert foreign_download.status_code == 404
    other_client.close()

    with session_factory() as db:
        file_record = db.get(SubmissionFile, uuid.UUID(file_data["id"]))
        assert file_record is not None
        file_record.storage_name = "../secret.pdf"
        file_record.scan_status = "clean"
        db.commit()
    traversal = client.get(
        f"/api/v1/author/submissions/{draft['id']}/files/{file_data['id']}"
    )
    assert traversal.status_code == 404
    with session_factory() as db:
        assert (
            db.get(Submission, uuid.UUID(draft["id"])).submitting_author_id == owner_id
        )
        assert db.get(User, other_id) is not None

    settings = get_settings()
    blocking_file = settings.private_storage_path.parent / f"blocker-{uuid.uuid4().hex}"
    blocking_file.write_text("file blocks directory creation", encoding="utf-8")
    settings.private_storage_path = blocking_file
    failed_write = client.post(
        f"/api/v1/author/submissions/{draft['id']}/files",
        files={"upload": ("failed-write.pdf", pdf, "application/pdf")},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert failed_write.status_code == 500
    blocking_file.unlink(missing_ok=True)


def test_role_change_revokes_sessions_and_idle_timeout(
    client: TestClient, session_factory
) -> None:
    admin_id, admin_secret, _ = create_user(
        session_factory, "roles-admin@example.test", "site_admin", mfa=True
    )
    target_id, _, _ = create_user(session_factory, "target@example.test", "author")
    login(client, "target@example.test")
    old_cookie = client.cookies.get("nsaj_session")

    admin_client = TestClient(client.app, raise_server_exceptions=False)
    admin_token = login_admin(
        admin_client, "roles-admin@example.test", admin_secret or ""
    )
    changed = admin_client.put(
        f"/api/v1/admin/users/{target_id}/roles",
        json={"roles": ["reviewer"]},
        headers={"X-CSRF-Token": admin_token},
    )
    assert changed.status_code == 200
    client.cookies.set("nsaj_session", old_cookie)
    assert client.get("/api/v1/auth/me").status_code == 401
    admin_client.close()

    user_id, _, _ = create_user(session_factory, "idle@example.test", "author")
    idle = TestClient(client.app, raise_server_exceptions=False)
    login(idle, "idle@example.test")
    with session_factory() as db:
        session = db.scalar(select(AuthSession).where(AuthSession.user_id == user_id))
        assert session is not None
        session.last_activity_at = datetime.now(UTC) - timedelta(minutes=31)
        db.commit()
    assert idle.get("/api/v1/auth/me").status_code == 401
    idle.close()
