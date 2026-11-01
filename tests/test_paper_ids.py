import re
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from test_editorial_publication import authenticate, seed_submission, seed_user

from app.core.config import Settings, get_settings
from app.models import ManuscriptReferenceCounter, Submission
from app.services.manuscript_references import MAX_REFERENCE_NUMBER


def test_paper_ids_are_generated_once_and_remain_owner_scoped(client, session_factory):
    author, _ = seed_user(session_factory, "paper-author@example.test", "author")
    seed_user(session_factory, "paper-other@example.test", "author")
    legacy_id, _ = seed_submission(session_factory, author, "draft")
    with session_factory() as db:
        legacy_reference = db.get(Submission, legacy_id).reference

    url = "/api/v1/author/submissions"
    assert client.post(url, json={}).status_code == 401
    csrf = authenticate(client, "paper-author@example.test")
    headers = {"X-CSRF-Token": csrf}
    assert client.post(url, json={}).status_code == 403
    assert (
        client.post(url, json={"reference": "NSH-999999"}, headers=headers).status_code
        == 422
    )
    first = client.post(url, json={"title": "First paper"}, headers=headers)
    second = client.post(url, json={"title": "Second paper"}, headers=headers)
    assert first.status_code == second.status_code == 201
    paper = first.json()
    prefix = re.escape(get_settings().manuscript_id_prefix)
    assert re.fullmatch(rf"{prefix}-\d{{8}}", paper["reference"])
    assert re.fullmatch(rf"{prefix}-\d{{8}}", second.json()["reference"])
    assert paper["reference"] != second.json()["reference"]
    assert paper["id"] != second.json()["id"]
    detail_url = f"{url}/{paper['id']}"
    assert client.get(detail_url).json()["reference"] == paper["reference"]
    updated = client.patch(detail_url, json={"title": "Updated title"}, headers=headers)
    assert updated.status_code == 200
    assert updated.json()["reference"] == paper["reference"]
    assert (
        client.patch(detail_url, json={"reference": "NSH-123456"}, headers=headers)
        .status_code
        == 422
    )
    assert client.get(f"{url}/{legacy_id}").json()["reference"] == legacy_reference

    # Prefix changes affect future papers; the global counter is never reset.
    get_settings().manuscript_id_prefix = "NSAJ"
    third = client.post(url, json={}, headers=headers)
    assert third.status_code == 201
    assert re.fullmatch(r"NSAJ-\d{8}", third.json()["reference"])
    assert client.get(detail_url).json()["reference"] == paper["reference"]
    authenticate(client, "paper-other@example.test")
    assert client.get(url).json()["items"] == []
    assert client.get(detail_url).status_code == 404
    assert client.get(f"{url}/{paper['reference']}").status_code == 422
    with session_factory() as db:
        stored_paper = db.get(Submission, uuid.UUID(paper["id"]))
        assert stored_paper.reference == paper["reference"]
        assert db.get(Submission, legacy_id).reference == legacy_reference


@pytest.mark.parametrize("role", ["reviewer", "site_admin"])
def test_other_roles_cannot_allocate_paper_ids(client, session_factory, role):
    _, secret = seed_user(
        session_factory, f"{role}@papers.test", role, mfa=role == "site_admin"
    )
    csrf = authenticate(client, f"{role}@papers.test", secret=secret)
    assert (
        client.post(
            "/api/v1/author/submissions", json={}, headers={"X-CSRF-Token": csrf}
        ).status_code
        == 403
    )
    with session_factory() as db:
        assert db.scalar(select(ManuscriptReferenceCounter)) is None


def test_reference_capacity_fails_without_creating_a_draft(client, session_factory):
    seed_user(session_factory, "capacity@papers.test", "author")
    with session_factory() as db:
        db.add(
            ManuscriptReferenceCounter(name="manuscript", value=MAX_REFERENCE_NUMBER)
        )
        db.commit()
    csrf = authenticate(client, "capacity@papers.test")
    response = client.post(
        "/api/v1/author/submissions", json={}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 503
    assert client.get("/api/v1/author/submissions").json()["items"] == []
    with session_factory() as db:
        counter = db.get(ManuscriptReferenceCounter, "manuscript")
        assert counter.value == MAX_REFERENCE_NUMBER


def test_paper_prefix_is_configurable_and_normalized(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PASSWORD", "test-only-password")
    monkeypatch.setenv("NSAJ_MANUSCRIPT_ID_PREFIX", " nsaj ")
    assert Settings().manuscript_id_prefix == "NSAJ"


@pytest.mark.parametrize("prefix", ["", "123", "N-SH", "ABCDEFGHI", "NSH/", "漢字"])
def test_invalid_paper_prefix_is_rejected(monkeypatch, prefix):
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PASSWORD", "test-only-password")
    monkeypatch.setenv("NSAJ_MANUSCRIPT_ID_PREFIX", prefix)
    with pytest.raises(ValidationError, match="Use 1 to 8 letters or digits"):
        Settings()
