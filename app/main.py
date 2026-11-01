import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.admin_workflow import router as admin_workflow_router
from app.api.overview import router as overview_router
from app.api.content import router as content_router
from app.api.editorial import router as editorial_router
from app.api.email_intake import router as email_router
from app.api.health import router as health_router
from app.api.publication import router as publication_router
from app.api.submission_intake import router as intake_router
from app.api.submissions import router as submissions_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_engine, get_session_factory
from app.services.content_schedule import publish_due
from app.services.email_intake import poll_mailbox
from app.services.mail_delivery import dispatch_pending


def run_background_jobs():
    # Separate transactions ensure mail failures do not roll back publication.
    with get_session_factory()() as db:
        if get_settings().content_scheduler_enabled:
            publish_due(db)
        dispatch_pending(db)
        poll_mailbox(db)
        dispatch_pending(db)


async def background_jobs():
    while True:
        try:
            await asyncio.to_thread(run_background_jobs)
        except Exception:
            logging.getLogger(__name__).warning(
                "Background job failed; will retry. "
                "Inspect database and mail configuration."
            )
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().app_env.casefold() == "test":
        import app.models  # noqa: F401

        Base.metadata.create_all(get_engine())
    task = (
        None
        if get_settings().app_env.casefold() == "test"
        else asyncio.create_task(background_jobs())
    )
    try:
        yield
    finally:
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="NSAJ API",
    description="Backend API for Noble Scientific Advances Journal",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(email_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(overview_router)
app.include_router(admin_workflow_router)
app.include_router(submissions_router)
app.include_router(intake_router)
app.include_router(editorial_router)
app.include_router(publication_router)
app.include_router(content_router)

if os.environ.get("APP_ENV", "").casefold() == "test":
    from app.api.test_support import router as test_support_router

    app.include_router(test_support_router)
