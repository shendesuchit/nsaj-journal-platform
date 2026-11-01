from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import UTC, datetime

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet
from fastapi import HTTPException, status

from app.core.config import get_settings

PASSWORDS = PasswordHasher(
    time_cost=2,
    memory_cost=19_456,
    parallelism=1,
    type=Type.ID,
)
PRIVILEGED_ROLES = {"site_admin", "editor_in_chief"}
KNOWN_ROLES = {
    "site_admin",
    "editor_in_chief",
    "managing_editor",
    "associate_editor",
    "editor",
    "reviewer",
    "author",
}


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_one_time_secret() -> str:
    return secrets.token_urlsafe(32)


def hash_password(password: str) -> str:
    return PASSWORDS.hash(password)


def verify_password(encoded: str | None, candidate: str) -> bool:
    if encoded is None:
        return False
    try:
        return PASSWORDS.verify(encoded, candidate)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def verify_password_policy(password: str) -> None:
    if len(password) < 12 or len(password) > 128:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be between 12 and 128 characters.",
        )


def _fernet() -> Fernet:
    secret = get_settings().mfa_encryption_key
    if secret is None:
        raise RuntimeError(
            "NSAJ_MFA_ENCRYPTION_KEY is required for privileged accounts"
        )
    try:
        return Fernet(secret.get_secret_value().encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError(
            "NSAJ_MFA_ENCRYPTION_KEY must be a valid Fernet key"
        ) from exc


def encrypt_totp_secret(secret: str) -> bytes:
    return _fernet().encrypt(secret.encode("ascii"))


def decrypt_totp_secret(secret: bytes) -> str:
    return _fernet().decrypt(secret).decode("ascii")


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, timestamp: int | None = None) -> str:
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp(secret: str, candidate: str, now: datetime | None = None) -> bool:
    if len(candidate) != 6 or not candidate.isdigit():
        return False
    timestamp = int((now or datetime.now(UTC)).timestamp())
    return any(
        hmac.compare_digest(totp_code(secret, timestamp + offset), candidate)
        for offset in (-30, 0, 30)
    )


def new_recovery_codes(count: int = 10) -> list[str]:
    return [secrets.token_hex(8).upper() for _ in range(count)]


def otpauth_uri(secret: str, email: str) -> str:
    from urllib.parse import quote

    label = quote(f"NSAJ:{email}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer=NSAJ&algorithm=SHA1&digits=6&period=30"
