from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    url = get_settings().sqlalchemy_url
    options = {"pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False}
        if url.database in {None, "", ":memory:"}:
            options["poolclass"] = StaticPool
    return create_engine(url, **options)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=get_engine(),
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()
