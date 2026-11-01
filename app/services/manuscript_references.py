"""Allocate stable paper references inside the draft creation transaction."""

import secrets

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ManuscriptReferenceCounter, Submission

MAX_REFERENCE_NUMBER = 999_999_999_999_999
RANDOM_SUFFIX_MIN = 10_000_000
RANDOM_SUFFIX_RANGE = 90_000_000
MAX_RANDOM_ATTEMPTS = 128


class ManuscriptReferenceUnavailable(Exception):
    """The configured paper reference namespace has reached its capacity."""


def allocate_manuscript_reference(db: Session) -> str:
    """Allocate a unique random numeric reference in the caller's transaction.

    Updating the shared counter serializes concurrent allocators until the draft
    commits. The random suffix is checked against existing references, and an
    aborted transaction releases the lock without creating a draft.
    """
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        insert = postgresql_insert
    elif dialect == "sqlite":
        insert = sqlite_insert
    else:
        raise RuntimeError("Paper IDs require PostgreSQL (or SQLite for tests).")
    counter = ManuscriptReferenceCounter
    number = db.scalar(
        insert(counter)
        .values(name="manuscript", value=1)
        .on_conflict_do_update(
            index_elements=[counter.name],
            set_={"value": counter.value + 1},
            where=counter.value < MAX_REFERENCE_NUMBER,
        )
        .returning(counter.value)
    )
    if number is None:
        raise ManuscriptReferenceUnavailable

    prefix = get_settings().manuscript_id_prefix
    for _ in range(MAX_RANDOM_ATTEMPTS):
        suffix = secrets.randbelow(RANDOM_SUFFIX_RANGE) + RANDOM_SUFFIX_MIN
        reference = f"{prefix}-{suffix}"
        existing = db.scalar(
            select(Submission.reference).where(Submission.reference == reference)
        )
        if existing is None:
            return reference
    raise ManuscriptReferenceUnavailable
