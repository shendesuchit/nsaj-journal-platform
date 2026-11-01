from __future__ import annotations

import argparse
import getpass
import re
import sys

from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models import MfaRecoveryCode, Role, User, UserMfa
from app.services.security import (
    encrypt_totp_secret,
    hash_password,
    hash_secret,
    new_recovery_codes,
    new_totp_secret,
)


def bootstrap_admin() -> int:
    try:
        settings = get_settings()
        if settings.privileged_mfa_required and settings.mfa_encryption_key is None:
            print(
                "NSAJ_MFA_ENCRYPTION_KEY must be configured before setup.",
                file=sys.stderr,
            )
            return 2
        db = get_session_factory()()
    except Exception:
        print(
            "Could not initialize the application database connection.", file=sys.stderr
        )
        return 2

    try:
        count = (
            db.scalar(
                select(func.count(User.id))
                .join(User.roles)
                .where(Role.name == "site_admin")
            )
            or 0
        )
        if count:
            print("A Site Admin already exists; no account was created.")
            return 1

        email = input("Site Admin email: ").strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            print("Enter a valid email address.", file=sys.stderr)
            return 2
        display_name = input("Display name: ").strip()
        if not display_name or len(display_name) > 200:
            print("Display name must contain 1 to 200 characters.", file=sys.stderr)
            return 2
        password = getpass.getpass("Password (12-128 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
        if len(password) < 12 or len(password) > 128 or password != confirmation:
            print("Passwords must match and be 12 to 128 characters.", file=sys.stderr)
            return 2
        if db.scalar(select(User.id).where(User.email == email)) is not None:
            print("An account already exists for that email.", file=sys.stderr)
            return 2

        role = db.scalar(select(Role).where(Role.name == "site_admin"))
        if role is None:
            role = Role(name="site_admin")
            db.add(role)
            db.flush()
        user = User(
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            roles=[role],
        )
        secret = None
        codes: list[str] = []
        if settings.privileged_mfa_required:
            secret = new_totp_secret()
            codes = new_recovery_codes()
            user.mfa = UserMfa(
                encrypted_totp_secret=encrypt_totp_secret(secret),
                enabled=True,
                recovery_codes=[
                    MfaRecoveryCode(code_hash=hash_secret(code)) for code in codes
                ],
            )
        db.add(user)
        db.commit()
        print("Site Admin created.")
        if secret is not None:
            print("Configure an authenticator now:")
            print(f"TOTP secret: {secret}")
            print(
                "One-use recovery codes (store securely; they will not be shown again):"
            )
            for code in codes:
                print(code)
            print("The secret and recovery codes are displayed once in this terminal.")
        return 0
    except Exception:
        db.rollback()
        print(
            "Site Admin setup did not complete; check migration and database state.",
            file=sys.stderr,
        )
        return 2
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="nsaj-admin")
    parser.add_argument(
        "command",
        choices=[
            "bootstrap-admin",
            "publish-due",
            "poll-email",
            "send-mail",
            "retry-mail",
            "import-email",
        ],
    )
    parser.add_argument("--file")
    args = parser.parse_args()
    if args.command == "bootstrap-admin":
        raise SystemExit(bootstrap_admin())
    from datetime import UTC, datetime

    from app.models import OutboundMail
    from app.services.content_schedule import publish_due
    from app.services.email_intake import ingest_message, poll_mailbox
    from app.services.mail_delivery import dispatch_pending

    with get_session_factory()() as db:
        if args.command == "publish-due":
            publish_due(db)
        elif args.command == "poll-email":
            poll_mailbox(db)
        elif args.command == "send-mail":
            dispatch_pending(db)
        elif args.command == "retry-mail":
            for row in db.scalars(
                select(OutboundMail).where(OutboundMail.status == "failed")
            ):
                row.status, row.attempts, row.next_attempt_at = (
                    "pending",
                    0,
                    datetime.now(UTC),
                )
            db.commit()
        elif args.command == "import-email":
            import asyncio
            from pathlib import Path

            if not args.file:
                parser.error("--file is required for import-email")
            asyncio.run(ingest_message(Path(args.file).read_bytes(), db))


if __name__ == "__main__":
    main()
