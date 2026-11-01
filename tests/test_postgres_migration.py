from sqlalchemy import inspect, text

from app.core.config import get_settings
from app.db.session import get_engine


def test_postgresql_identity_and_submission_migration_is_applied() -> None:
    engine = get_engine()
    assert get_settings().sqlalchemy_url.get_backend_name() == "postgresql"
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
        submission_checks = {
            item[0]
            for item in connection.execute(
                text(
                    "SELECT conname FROM pg_constraint "
                    "WHERE conrelid = 'submissions'::regclass AND contype = 'c'"
                )
            ).all()
        }
    assert revision == "8e5d7a3c9b10"
    assert {
        "submission_checklists",
        "submission_receipts",
        "manuscript_reference_counters",
        "users",
        "roles",
        "auth_sessions",
        "invitations",
        "password_recoveries",
        "user_mfa",
        "mfa_recovery_codes",
        "audit_events",
        "submissions",
        "submission_authors",
        "submission_files",
        "submission_workflow_events",
        "editor_assignments",
        "reviewer_profiles",
        "review_assignments",
        "review_reports",
        "editorial_decisions",
        "submission_revisions",
        "volumes",
        "issues",
        "articles",
        "article_authors",
        "article_scholarly_actions",
        "calls_for_papers",
        "public_pages",
        "template_resources",
    }.issubset(tables)
    assert "ck_submissions_status" in submission_checks
    assert "ck_submissions_draft_only" not in submission_checks
