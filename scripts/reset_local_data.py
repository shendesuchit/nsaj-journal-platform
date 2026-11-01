"""Clear local NSAJ walkthrough data while retaining existing user accounts.

Run from the repository root with the project's virtual environment. This tool
is intentionally restricted to a local PostgreSQL database named ``nsaj_dev``
and requires an exact interactive confirmation before changing anything.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from sqlalchemy import text

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

import app.models  # noqa: E402, F401 - populate the SQLAlchemy metadata.
from app.core.config import get_settings  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_engine  # noqa: E402

CONFIRMATION = "RESET NSAJ DEV DATA"
PRESERVED_TABLES = {
    "users",
    "roles",
    "user_roles",
    "user_mfa",
    "mfa_recovery_codes",
    # The allocator is intentionally retained so paper ID history is not reset.
    "manuscript_reference_counters",
}


def local_directory(configured_path: Path, label: str) -> Path:
    candidate = configured_path
    if not candidate.is_absolute():
        candidate = REPOSITORY_ROOT / candidate
    if candidate.is_symlink():
        raise RuntimeError(f"Refusing to clear {label}: its path is a symlink.")

    resolved = candidate.resolve()
    if resolved == REPOSITORY_ROOT or REPOSITORY_ROOT not in resolved.parents:
        raise RuntimeError(
            f"Refusing to clear {label}: configure it inside this repository first."
        )
    if resolved.exists() and not resolved.is_dir():
        raise RuntimeError(f"Refusing to clear {label}: its path is not a directory.")
    return resolved


def clear_directory_contents(path: Path) -> int:
    if not path.exists():
        return 0

    removed = 0
    for child in path.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)
        removed += 1
    return removed


def count_rows(connection, table_names: list[str], quote) -> tuple[int, int]:
    total = 0
    for name in table_names:
        total += connection.execute(
            text(f"SELECT COUNT(*) FROM {quote(name)}")
        ).scalar_one()
    users = connection.execute(text("SELECT COUNT(*) FROM \"users\"")).scalar_one()
    return users, total


def main() -> int:
    os.chdir(REPOSITORY_ROOT)

    try:
        settings = get_settings()
        url = settings.sqlalchemy_url
        if settings.app_env.casefold() != "development":
            raise RuntimeError("APP_ENV must be development.")
        if url.get_backend_name() != "postgresql":
            raise RuntimeError("The reset is allowed only for PostgreSQL.")
        if url.database != "nsaj_dev" or url.host not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise RuntimeError(
                "The reset is restricted to local PostgreSQL database nsaj_dev."
            )

        private_files = local_directory(
            settings.private_storage_path, "private manuscript files"
        )
        captured_mail = local_directory(settings.mail_capture_path, "captured mail")
        engine = get_engine()
        quote = engine.dialect.identifier_preparer.quote
        table_names = sorted(
            name for name in Base.metadata.tables if name not in PRESERVED_TABLES
        )

        with engine.connect() as connection:
            user_count, row_count = count_rows(connection, table_names, quote)

        print("Local NSAJ data reset")
        print(f"Database: PostgreSQL at {url.host}, database {url.database}")
        print(f"Existing accounts and role assignments retained: {user_count}")
        print(
            f"Application rows to clear: {row_count} "
            f"across {len(table_names)} tables"
        )
        print(
            "Declaration checklists, manuscripts, workflow/audit records, "
            "and content will be cleared."
        )
        print(f"Private files under: {private_files}")
        print(f"Captured invitation/recovery mail under: {captured_mail}")
        print(
            "The schema, passwords, roles, MFA setup, and paper ID allocator "
            "are retained."
        )
        if input(f'Type "{CONFIRMATION}" to continue: ').strip() != CONFIRMATION:
            print("Reset cancelled; no data was changed.")
            return 1

        quoted_tables = ", ".join(quote(name) for name in table_names)
        with engine.begin() as connection:
            connection.execute(
                text(f"TRUNCATE TABLE {quoted_tables} RESTART IDENTITY CASCADE")
            )

        try:
            file_count = clear_directory_contents(private_files)
            mail_count = clear_directory_contents(captured_mail)
        except OSError:
            print(
                "Database records were cleared, but one local file directory "
                "could not be cleaned. "
                "Review the paths printed above and remove its contents manually.",
                file=sys.stderr,
            )
            return 2

        print(
            f"Reset complete. Removed {row_count} database rows, "
            f"{file_count} private-file entries, and "
            f"{mail_count} captured-mail entries."
        )
        print("Your existing users can sign in again; active sessions were cleared.")
        return 0
    except Exception as error:
        print(f"Reset stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
