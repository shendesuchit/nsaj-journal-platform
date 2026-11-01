from __future__ import annotations

import hmac
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    AuditEvent,
    AuthSession,
    Invitation,
    LoginFailure,
    MfaRecoveryCode,
    PasswordRecovery,
    ReviewAssignment,
    ReviewerProfile,
    Role,
    User,
    UserMfa,
)
from app.services.mail_delivery import queue_message, require_delivery
from app.services.security import (
    KNOWN_ROLES,
    PRIVILEGED_ROLES,
    decrypt_totp_secret,
    encrypt_totp_secret,
    hash_password,
    hash_secret,
    new_one_time_secret,
    new_recovery_codes,
    new_totp_secret,
    normalize_email,
    otpauth_uri,
    verify_password,
    verify_password_policy,
    verify_totp,
)

router = APIRouter(prefix="/api/v1", tags=["identity"])
DB = Annotated[Session, Depends(get_db)]
SESSION_COOKIE = "nsaj_session"
CSRF_COOKIE = "nsaj_csrf"
GENERIC_AUTH_ERROR = "The supplied credentials or one-time link are invalid or expired."


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginInput(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class InviteInput(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    role: str


class RegistrationInput(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)


class AcceptInvitationInput(StrictModel):
    token: str = Field(min_length=30, max_length=200)
    password: str = Field(min_length=12, max_length=128)


class TokenInput(StrictModel):
    token: str = Field(min_length=30, max_length=200)


class RecoveryInput(TokenInput):
    password: str = Field(min_length=12, max_length=128)


class RecoveryRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)


class MfaInput(StrictModel):
    code: str = Field(min_length=6, max_length=32)


class PasswordChangeInput(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class RoleUpdateInput(StrictModel):
    roles: list[str] = Field(min_length=1, max_length=7)


class UserActiveInput(StrictModel):
    is_active: bool


class SessionContext:
    def __init__(self, user: User, session: AuthSession):
        self.user = user
        self.session = session


def _now() -> datetime:
    return datetime.now(UTC)


def _is_expired(value: datetime, now: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value <= now


def _roles(user: User) -> set[str]:
    return {role.name for role in user.roles}


def _audit(
    db: Session,
    event: str,
    actor: uuid.UUID | None,
    target_type: str | None = None,
    target_id: uuid.UUID | str | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            actor_id=actor,
            event_type=event,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details or {},
        )
    )


def _ensure_role(db: Session, name: str) -> Role:
    role = db.scalar(select(Role).where(Role.name == name))
    if role is None:
        role = Role(name=name)
        db.add(role)
        db.flush()
    return role


def _issue_session(
    response: Response, db: Session, user: User, *, mfa_verified: bool
) -> tuple[AuthSession, dict[str, str]]:
    settings = get_settings()
    session_token = new_one_time_secret()
    csrf_token = new_one_time_secret()
    session = AuthSession(
        user_id=user.id,
        token_hash=hash_secret(session_token),
        csrf_hash=hash_secret(csrf_token),
        mfa_verified=mfa_verified,
        last_activity_at=_now(),
        absolute_expires_at=_now() + timedelta(hours=settings.session_absolute_hours),
    )
    db.add(session)
    db.flush()
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        secure=settings.app_env.casefold() not in {"development", "test"},
        samesite="lax",
        max_age=settings.session_absolute_hours * 3600,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=settings.app_env.casefold() not in {"development", "test"},
        samesite="lax",
        max_age=settings.session_absolute_hours * 3600,
        path="/",
    )
    return session, {"csrf_token": csrf_token}


def _clear_session_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.app_env.casefold() not in {"development", "test"},
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        secure=settings.app_env.casefold() not in {"development", "test"},
        samesite="lax",
    )


def _require_pre_auth_csrf(request: Request) -> None:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def get_session_context(request: Request, db: DB) -> SessionContext:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required.")
    session = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_secret(token))
    )
    if session is None or session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    now = _now()
    idle_limit = now - timedelta(minutes=get_settings().session_idle_minutes)
    last_activity = session.last_activity_at
    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=UTC)
    if _is_expired(session.absolute_expires_at, now) or last_activity < idle_limit:
        session.revoked_at = now
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired.")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Authentication required.")
    session.last_activity_at = now
    db.commit()
    return SessionContext(user, session)


def get_authenticated_user(
    context: Annotated[SessionContext, Depends(get_session_context)],
) -> User:
    role_names = _roles(context.user)
    mfa_enabled = bool(context.user.mfa and context.user.mfa.enabled)
    if (
        get_settings().privileged_mfa_required
        and role_names & PRIVILEGED_ROLES
        and (not mfa_enabled or not context.session.mfa_verified)
    ):
        raise HTTPException(
            status_code=403, detail="Multi-factor authentication is required."
        )
    return context.user


def get_author_user(
    user: Annotated[User, Depends(get_authenticated_user)],
) -> User:
    if "author" not in _roles(user):
        raise HTTPException(status_code=403, detail="An Author role is required.")
    return user


def require_csrf(
    request: Request, context: Annotated[SessionContext, Depends(get_session_context)]
) -> None:
    cookie = request.cookies.get(CSRF_COOKIE, "")
    header = request.headers.get("x-csrf-token", "")
    if (
        not cookie
        or not header
        or not hmac.compare_digest(cookie, header)
        or not hmac.compare_digest(hash_secret(cookie), context.session.csrf_hash)
    ):
        raise HTTPException(status_code=403, detail="CSRF validation failed.")


def require_admin(user: Annotated[User, Depends(get_authenticated_user)]) -> User:
    if "site_admin" not in _roles(user):
        raise HTTPException(
            status_code=403, detail="This action requires a Site Admin role."
        )
    return user


def _create_pending_mfa(db: Session, user: User) -> tuple[str, list[str]]:
    secret = new_totp_secret()
    if user.mfa is not None:
        db.delete(user.mfa)
        db.flush()
    mfa = UserMfa(
        user_id=user.id,
        encrypted_totp_secret=encrypt_totp_secret(secret),
        enabled=False,
    )
    codes = new_recovery_codes()
    mfa.recovery_codes = [
        MfaRecoveryCode(code_hash=hash_secret(code)) for code in codes
    ]
    db.add(mfa)
    db.flush()
    return secret, codes


def _login_status(user: User, session: AuthSession, csrf: dict[str, str]) -> dict:
    role_names = _roles(user)
    mfa_required = get_settings().privileged_mfa_required and bool(
        role_names & PRIVILEGED_ROLES
    )
    mfa_enabled = bool(user.mfa and user.mfa.enabled)
    if mfa_required and not mfa_enabled:
        secret = (
            decrypt_totp_secret(user.mfa.encrypted_totp_secret) if user.mfa else None
        )
        return {
            "authenticated": False,
            "mfa_setup_required": True,
            "mfa_secret": secret,
            "otpauth_uri": otpauth_uri(secret, user.email) if secret else None,
            "recovery_codes": [],
            **csrf,
        }
    if mfa_required and not session.mfa_verified:
        return {"authenticated": False, "mfa_required": True, **csrf}
    return {
        "authenticated": True,
        "mfa_required": False,
        "mfa_setup_required": False,
        **csrf,
    }


@router.get("/auth/csrf")
def issue_pre_auth_csrf(response: Response) -> dict[str, str]:
    settings = get_settings()
    token = new_one_time_secret()
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,
        secure=settings.app_env.casefold() not in {"development", "test"},
        samesite="lax",
        path="/",
    )
    return {"csrf_token": token}


@router.post("/auth/login")
def login(payload: LoginInput, request: Request, response: Response, db: DB) -> dict:
    _require_pre_auth_csrf(request)
    email = normalize_email(payload.email)
    settings = get_settings()
    window_start = _now() - timedelta(minutes=settings.login_failure_window_minutes)
    failure_count = (
        db.scalar(
            select(func.count(LoginFailure.id)).where(
                LoginFailure.email == email, LoginFailure.failed_at >= window_start
            )
        )
        or 0
    )
    if failure_count >= settings.login_failure_limit:
        raise HTTPException(
            status_code=429, detail="Too many failed sign-in attempts. Try again later."
        )

    user = db.scalar(select(User).where(User.email == email))
    if (
        user is None
        or not user.is_active
        or not verify_password(user.password_hash, payload.password)
    ):
        db.add(LoginFailure(email=email, failed_at=_now()))
        _audit(db, "auth.login_failed", None)
        db.commit()
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    db.execute(delete(LoginFailure).where(LoginFailure.email == email))
    role_names = _roles(user)
    mfa_required = settings.privileged_mfa_required and bool(
        role_names & PRIVILEGED_ROLES
    )
    mfa_enabled = bool(user.mfa and user.mfa.enabled)
    setup_secret = None
    setup_recovery_codes: list[str] = []
    if mfa_required and not mfa_enabled:
        setup_secret, setup_recovery_codes = _create_pending_mfa(db, user)
    session, csrf = _issue_session(response, db, user, mfa_verified=not mfa_required)
    _audit(db, "auth.login_succeeded", user.id, "user", user.id)
    db.commit()
    result = _login_status(user, session, csrf)
    if setup_secret:
        result.update(
            {
                "mfa_setup_required": True,
                "mfa_secret": setup_secret,
                "otpauth_uri": otpauth_uri(setup_secret, user.email),
                "recovery_codes": setup_recovery_codes,
            }
        )
    elif mfa_required and not mfa_enabled:
        secret = decrypt_totp_secret(user.mfa.encrypted_totp_secret)
        result.update(
            {
                "mfa_setup_required": True,
                "mfa_secret": secret,
                "otpauth_uri": otpauth_uri(secret, user.email),
            }
        )
    return result


@router.post("/auth/logout", dependencies=[Depends(require_csrf)])
def logout(
    response: Response,
    context: Annotated[SessionContext, Depends(get_session_context)],
    db: DB,
) -> dict[str, bool]:
    context.session.revoked_at = _now()
    _audit(db, "auth.logout", context.user.id, "session", context.session.id)
    db.commit()
    _clear_session_cookies(response)
    return {"ok": True}


@router.get("/auth/me")
def current_user(
    context: Annotated[SessionContext, Depends(get_session_context)],
) -> dict:
    user = context.user
    mfa_required = get_settings().privileged_mfa_required and bool(
        _roles(user) & PRIVILEGED_ROLES
    )
    return {
        "id": str(user.id),
        "email": user.email,
        "display_name": user.display_name,
        "roles": sorted(_roles(user)),
        "authenticated": context.session.mfa_verified or not mfa_required,
        "mfa_required": mfa_required and not context.session.mfa_verified,
        "mfa_setup_required": mfa_required and not bool(user.mfa and user.mfa.enabled),
    }


@router.post("/auth/mfa/setup/confirm", dependencies=[Depends(require_csrf)])
def confirm_mfa_setup(
    payload: MfaInput,
    context: Annotated[SessionContext, Depends(get_session_context)],
    db: DB,
) -> dict:
    user = context.user
    if not (_roles(user) & PRIVILEGED_ROLES):
        raise HTTPException(
            status_code=400, detail="This account does not require MFA setup."
        )
    mfa = user.mfa
    if mfa is None or mfa.enabled:
        raise HTTPException(status_code=409, detail="MFA setup is not pending.")
    if not verify_totp(decrypt_totp_secret(mfa.encrypted_totp_secret), payload.code):
        raise HTTPException(status_code=400, detail="The MFA code is invalid.")
    mfa.enabled = True
    context.session.mfa_verified = True
    _audit(db, "auth.mfa_enabled", user.id, "user", user.id)
    db.commit()
    return {"ok": True}


@router.post("/auth/mfa/verify", dependencies=[Depends(require_csrf)])
def verify_mfa(
    payload: MfaInput,
    context: Annotated[SessionContext, Depends(get_session_context)],
    db: DB,
) -> dict[str, bool]:
    user = context.user
    if (
        not (_roles(user) & PRIVILEGED_ROLES)
        or user.mfa is None
        or not user.mfa.enabled
    ):
        raise HTTPException(
            status_code=400, detail="MFA verification is not available."
        )
    mfa = user.mfa
    valid = verify_totp(decrypt_totp_secret(mfa.encrypted_totp_secret), payload.code)
    if not valid:
        code_hash = hash_secret(payload.code.strip().upper())
        recovery = db.scalar(
            select(MfaRecoveryCode).where(
                MfaRecoveryCode.user_id == user.id,
                MfaRecoveryCode.code_hash == code_hash,
                MfaRecoveryCode.used_at.is_(None),
            )
        )
        if recovery is not None:
            recovery.used_at = _now()
            valid = True
    if not valid:
        raise HTTPException(status_code=401, detail="The MFA code is invalid.")
    context.session.mfa_verified = True
    _audit(db, "auth.mfa_verified", user.id, "session", context.session.id)
    db.commit()
    return {"ok": True}


@router.post("/auth/password/change", dependencies=[Depends(require_csrf)])
def change_password(
    payload: PasswordChangeInput,
    context: Annotated[SessionContext, Depends(get_session_context)],
    db: DB,
) -> dict[str, bool]:
    verify_password_policy(payload.new_password)
    if not verify_password(context.user.password_hash, payload.current_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    context.user.password_hash = hash_password(payload.new_password)
    db.execute(
        AuthSession.__table__.update()
        .where(AuthSession.user_id == context.user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    _audit(db, "auth.password_changed", context.user.id, "user", context.user.id)
    db.commit()
    return {"ok": True}


@router.post("/invitations", dependencies=[Depends(require_csrf)])
def create_invitation(
    payload: InviteInput,
    db: DB,
    actor: Annotated[User, Depends(require_admin)],
) -> dict[str, str | bool]:
    if payload.role not in KNOWN_ROLES:
        raise HTTPException(status_code=422, detail="Unknown role.")
    email = normalize_email(payload.email)
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(
            status_code=422, detail="A valid email address is required."
        )
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise HTTPException(
            status_code=409, detail="An account already exists for that email."
        )
    require_delivery()
    token = new_one_time_secret()
    role = _ensure_role(db, payload.role)
    invitation = Invitation(
        email=email,
        display_name=payload.display_name.strip(),
        role_id=role.id,
        token_hash=hash_secret(token),
        invited_by_id=actor.id,
        expires_at=_now() + timedelta(hours=get_settings().token_expiry_hours),
    )
    db.add(invitation)
    db.flush()
    link = (
        f"{get_settings().public_base_url.rstrip('/')}/accept-invitation#token={token}"
    )
    queue_message(db, recipient=email, subject="NSAJ account invitation", link=link)
    _audit(
        db,
        "identity.invitation_created",
        actor.id,
        "invitation",
        invitation.id,
        {"role": payload.role},
    )
    db.commit()
    return {
        "ok": True,
        "message": "Invitation queued for delivery.",
    }


@router.post("/auth/register", status_code=202)
def register_author(payload: RegistrationInput, request: Request, db: DB) -> dict:
    _require_pre_auth_csrf(request)
    require_delivery()
    email = normalize_email(payload.email)
    if not payload.display_name.strip() or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "A name and valid email address are required.")
    source = hash_secret("signup:" + (request.client.host if request.client else "unknown"))
    attempts = db.scalar(select(func.count()).select_from(AuditEvent).where(
        AuditEvent.event_type == "identity.signup_requested", AuditEvent.target_id == source,
        AuditEvent.created_at >= _now() - timedelta(hours=1))) or 0
    if attempts >= 20:
        raise HTTPException(429, "Too many signup requests. Try again later.")
    _audit(db, "identity.signup_requested", None, "registration", source)
    recent = db.scalar(select(func.count()).select_from(Invitation).where(
        Invitation.email == email, Invitation.created_at >= _now() - timedelta(days=1))) or 0
    if recent < 5 and db.scalar(select(User.id).where(User.email == email)) is None:
        token = new_one_time_secret()
        role = _ensure_role(db, "author")
        db.add(Invitation(email=email, display_name=payload.display_name.strip(), role_id=role.id,
            token_hash=hash_secret(token), invited_by_id=None,
            expires_at=_now()+timedelta(hours=get_settings().token_expiry_hours)))
        link = f"{get_settings().public_base_url.rstrip('/')}/accept-invitation#token={token}"
        queue_message(db, recipient=email, subject="Verify your NSAJ author account", link=link)
    db.commit()
    return {"ok": True, "message": "Check your inbox for a setup link. Already registered? Sign in or reset your password."}


@router.post("/invitations/accept")
def accept_invitation(
    payload: AcceptInvitationInput, request: Request, response: Response, db: DB
) -> dict:
    _require_pre_auth_csrf(request)
    verify_password_policy(payload.password)
    invitation = db.scalar(
        select(Invitation).where(Invitation.token_hash == hash_secret(payload.token))
    )
    if (
        invitation is None
        or invitation.used_at is not None
        or _is_expired(invitation.expires_at, _now())
    ):
        raise HTTPException(status_code=400, detail=GENERIC_AUTH_ERROR)
    if db.scalar(select(User.id).where(User.email == invitation.email)) is not None:
        raise HTTPException(
            status_code=409, detail="An account already exists for that email."
        )
    role = db.get(Role, invitation.role_id)
    if role is None:
        raise HTTPException(status_code=400, detail=GENERIC_AUTH_ERROR)
    user = User(
        email=invitation.email,
        display_name=invitation.display_name,
        password_hash=hash_password(payload.password),
    )
    user.roles = [role]
    db.add(user)
    db.flush()
    if role.name == "reviewer":
        reviewer_profile = db.scalar(
            select(ReviewerProfile).where(ReviewerProfile.email == invitation.email)
        )
        if reviewer_profile is None:
            reviewer_profile = ReviewerProfile(
                user_id=user.id,
                email=invitation.email,
                full_name=invitation.display_name,
                created_by_id=invitation.invited_by_id,
            )
            db.add(reviewer_profile)
            db.flush()
        else:
            reviewer_profile.user_id = user.id
        db.execute(
            ReviewAssignment.__table__.update()
            .where(
                ReviewAssignment.reviewer_profile_id == reviewer_profile.id,
                ReviewAssignment.reviewer_user_id.is_(None),
            )
            .values(reviewer_user_id=user.id)
        )
    invitation.used_at = _now()
    mfa_setup = None
    mfa_required = (
        get_settings().privileged_mfa_required and role.name in PRIVILEGED_ROLES
    )
    if mfa_required:
        secret, recovery_codes = _create_pending_mfa(db, user)
        mfa_setup = {
            "secret": secret,
            "otpauth_uri": otpauth_uri(secret, user.email),
            "recovery_codes": recovery_codes,
        }
    _, csrf = _issue_session(response, db, user, mfa_verified=not mfa_required)
    _audit(
        db,
        "identity.invitation_accepted",
        user.id,
        "user",
        user.id,
        {"role": role.name},
    )
    db.commit()
    return {"ok": True, "role": role.name, "mfa_setup": mfa_setup, **csrf}


@router.post("/auth/recovery/request")
def request_recovery(
    payload: RecoveryRequest, request: Request, db: DB
) -> dict[str, str | bool]:
    _require_pre_auth_csrf(request)
    require_delivery()
    email = normalize_email(payload.email)
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if user is not None:
        token = new_one_time_secret()
        recovery = PasswordRecovery(
            user_id=user.id,
            token_hash=hash_secret(token),
            expires_at=_now() + timedelta(hours=get_settings().token_expiry_hours),
        )
        db.add(recovery)
        db.flush()
        link = f"{get_settings().public_base_url.rstrip('/')}/recover#token={token}"
        queue_message(db, recipient=email, subject="NSAJ password recovery", link=link)
        _audit(db, "auth.recovery_requested", user.id, "user", user.id)
        db.commit()
    return {
        "ok": True,
        "message": "If the account exists, recovery instructions have been sent.",
    }


@router.post("/auth/recovery/complete")
def complete_recovery(
    payload: RecoveryInput, request: Request, response: Response, db: DB
) -> dict[str, bool]:
    _require_pre_auth_csrf(request)
    verify_password_policy(payload.password)
    recovery = db.scalar(
        select(PasswordRecovery).where(
            PasswordRecovery.token_hash == hash_secret(payload.token)
        )
    )
    if (
        recovery is None
        or recovery.used_at is not None
        or _is_expired(recovery.expires_at, _now())
    ):
        raise HTTPException(status_code=400, detail=GENERIC_AUTH_ERROR)
    user = db.get(User, recovery.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail=GENERIC_AUTH_ERROR)
    user.password_hash = hash_password(payload.password)
    recovery.used_at = _now()
    db.execute(
        AuthSession.__table__.update()
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    _audit(db, "auth.password_recovered", user.id, "user", user.id)
    db.commit()
    _clear_session_cookies(response)
    return {"ok": True}


@router.put("/admin/users/{user_id}/roles", dependencies=[Depends(require_csrf)])
def update_roles(
    user_id: uuid.UUID,
    payload: RoleUpdateInput,
    db: DB,
    actor: Annotated[User, Depends(require_admin)],
) -> dict[str, list[str]]:
    requested = set(payload.roles)
    if not requested or not requested.issubset(KNOWN_ROLES):
        raise HTTPException(status_code=422, detail="One or more roles are unknown.")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    current = _roles(user)
    if "site_admin" in current and "site_admin" not in requested:
        admin_count = (
            db.scalar(
                select(func.count(User.id))
                .join(User.roles)
                .where(Role.name == "site_admin", User.is_active.is_(True))
            )
            or 0
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=409, detail="The last active Site Admin cannot be removed."
            )
    user.roles = [_ensure_role(db, name) for name in sorted(requested)]
    db.execute(
        AuthSession.__table__.update()
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    _audit(
        db,
        "identity.roles_changed",
        actor.id,
        "user",
        user.id,
        {"roles": sorted(requested)},
    )
    db.commit()
    return {"roles": sorted(requested)}


@router.get("/admin/users")
def list_users(
    db: DB, actor: Annotated[User, Depends(require_admin)]
) -> dict[str, list[dict]]:
    users = db.scalars(select(User).order_by(User.created_at.desc())).all()
    return {
        "items": [
            {
                "id": str(user.id),
                "email": user.email,
                "display_name": user.display_name,
                "roles": sorted(_roles(user)),
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            }
            for user in users
        ]
    }


@router.put("/admin/users/{user_id}/active", dependencies=[Depends(require_csrf)])
def set_user_active(
    user_id: uuid.UUID,
    payload: UserActiveInput,
    db: DB,
    actor: Annotated[User, Depends(require_admin)],
) -> dict[str, bool]:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.is_active and not payload.is_active and "site_admin" in _roles(user):
        admin_count = (
            db.scalar(
                select(func.count(User.id))
                .join(User.roles)
                .where(Role.name == "site_admin", User.is_active.is_(True))
            )
            or 0
        )
        if admin_count <= 1:
            raise HTTPException(
                status_code=409,
                detail="The last active Site Admin cannot be deactivated.",
            )
    user.is_active = payload.is_active
    if not user.is_active:
        db.execute(
            AuthSession.__table__.update()
            .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
    _audit(
        db,
        "identity.account_status_changed",
        actor.id,
        "user",
        user.id,
        {"is_active": user.is_active},
    )
    db.commit()
    return {"is_active": user.is_active}
