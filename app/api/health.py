from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_engine

router = APIRouter(tags=["Health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """Compatibility liveness endpoint; does not depend on the database."""
    return {"status": "ok", "service": "nsaj-api"}


@router.get("/health/live")
def liveness_check() -> dict[str, str]:
    return {"status": "ok", "service": "nsaj-api"}


@router.get("/health/ready")
def readiness_check() -> dict[str, str]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready",
        ) from exc

    return {"status": "ready", "service": "nsaj-api"}
