from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import MfaRecoveryCode, Role, User, UserMfa
from app.services.security import (
    KNOWN_ROLES,
    PRIVILEGED_ROLES,
    encrypt_totp_secret,
    hash_password,
    hash_secret,
    new_recovery_codes,
    new_totp_secret,
)

router = APIRouter(prefix="/__test__", include_in_schema=False)


class SeedUserInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    role: str


@router.post("/seed-user")
def seed_user(
    payload: SeedUserInput,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, str | None]:
    if get_settings().app_env.casefold() != "test":
        raise HTTPException(status_code=404, detail="Not found.")
    email = payload.email.strip().casefold()
    if payload.role not in KNOWN_ROLES:
        raise HTTPException(status_code=422, detail="Unknown role.")
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(status_code=409, detail="Test account already exists.")
    role = db.scalar(select(Role).where(Role.name == payload.role))
    if role is None:
        role = Role(name=payload.role)
        db.add(role)
        db.flush()
    user = User(
        email=email,
        display_name="Test User",
        password_hash=hash_password(payload.password),
        roles=[role],
    )
    secret = None
    if payload.role in PRIVILEGED_ROLES:
        secret = new_totp_secret()
        user.mfa = UserMfa(
            encrypted_totp_secret=encrypt_totp_secret(secret),
            enabled=True,
            recovery_codes=[
                MfaRecoveryCode(code_hash=hash_secret(code))
                for code in new_recovery_codes()
            ],
        )
    db.add(user)
    db.commit()
    return {"email": email, "mfa_secret": secret}
