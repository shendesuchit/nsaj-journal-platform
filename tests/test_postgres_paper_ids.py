import re
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    Engine,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import get_settings
from app.models import ManuscriptReferenceCounter
from app.services.manuscript_references import (
    MAX_REFERENCE_NUMBER,
    ManuscriptReferenceUnavailable,
    allocate_manuscript_reference,
)

PostgresCase = tuple[Engine, str, Table]


@pytest.fixture
def isolated_paper_schema() -> Iterator[PostgresCase]:
    """Exercise PostgreSQL without reading or updating the application counter."""
    url = get_settings().sqlalchemy_url
    assert url.get_backend_name() == "postgresql"
    schema = f"test_paper_ids_{uuid4().hex}"
    engine = create_engine(url, pool_pre_ping=True)
    scoped_engine = engine.execution_options(schema_translate_map={None: schema})
    submissions = Table(
        "submissions",
        MetaData(),
        Column("reference", String(24), primary_key=True),
    )
    with engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    try:
        ManuscriptReferenceCounter.__table__.create(scoped_engine)
        submissions.create(scoped_engine)
        yield scoped_engine, schema, submissions
    finally:
        # No CASCADE: remove only the objects this fixture owns, and fail if any
        # unexpected objects remain instead of deleting them implicitly.
        with scoped_engine.begin() as connection:
            ManuscriptReferenceCounter.__table__.drop(connection, checkfirst=True)
            submissions.drop(connection, checkfirst=True)
            connection.execute(DropSchema(schema))
        engine.dispose()


def assert_random_reference(reference: str) -> None:
    prefix = get_settings().manuscript_id_prefix
    assert re.fullmatch(rf"{prefix}-\d{{8}}", reference)


def test_concurrent_first_use_allocates_distinct_committed_paper_ids(
    isolated_paper_schema: PostgresCase,
) -> None:
    engine, _, submissions = isolated_paper_schema
    workers = 8
    barrier = Barrier(workers)

    def create_paper() -> str:
        # Synchronize before opening a connection, avoiding a barrier waiting
        # for workers that are themselves waiting for the connection pool.
        barrier.wait(timeout=15)
        with Session(engine) as db, db.begin():
            reference = allocate_manuscript_reference(db)
            db.execute(insert(submissions).values(reference=reference))
            return reference

    with ThreadPoolExecutor(max_workers=workers) as executor:
        references = list(executor.map(lambda _: create_paper(), range(workers)))

    assert len(references) == workers
    assert len(set(references)) == workers
    for reference in references:
        assert_random_reference(reference)
    with Session(engine) as db:
        counter = db.get(ManuscriptReferenceCounter, "manuscript")
        assert counter is not None
        assert counter.value == workers


@pytest.mark.parametrize("previous_value", [None, 7])
def test_failed_draft_transaction_rolls_back_allocation(
    isolated_paper_schema: PostgresCase, previous_value: int | None
) -> None:
    engine, _, _ = isolated_paper_schema
    with Session(engine) as db:
        if previous_value is not None:
            db.add(ManuscriptReferenceCounter(name="manuscript", value=previous_value))
            db.commit()
        transaction = db.begin()
        assert_random_reference(allocate_manuscript_reference(db))
        transaction.rollback()
        counter = db.get(ManuscriptReferenceCounter, "manuscript")
        assert (counter.value if counter is not None else None) == previous_value
        db.rollback()
        with db.begin():
            assert_random_reference(allocate_manuscript_reference(db))
    with Session(engine) as db:
        counter = db.get(ManuscriptReferenceCounter, "manuscript")
        assert counter is not None
        assert counter.value == (previous_value or 0) + 1


@pytest.mark.parametrize("invalid_value", [-1, MAX_REFERENCE_NUMBER + 1])
def test_postgresql_rejects_counter_values_outside_capacity(
    isolated_paper_schema: PostgresCase, invalid_value: int
) -> None:
    engine, _, _ = isolated_paper_schema
    with Session(engine) as db:
        db.add(ManuscriptReferenceCounter(name="manuscript", value=invalid_value))
        with pytest.raises(IntegrityError) as failure:
            db.commit()
        assert (
            failure.value.orig.diag.constraint_name
            == "ck_manuscript_reference_counters_value"
        )
        db.rollback()
        assert db.get(ManuscriptReferenceCounter, "manuscript") is None


def test_capacity_is_reported_without_wrapping_or_mutating_counter(
    isolated_paper_schema: PostgresCase,
) -> None:
    engine, _, _ = isolated_paper_schema
    with Session(engine) as db:
        db.add(
            ManuscriptReferenceCounter(
                name="manuscript", value=MAX_REFERENCE_NUMBER - 1
            )
        )
        db.commit()
        assert_random_reference(allocate_manuscript_reference(db))
        db.commit()
        with pytest.raises(ManuscriptReferenceUnavailable):
            allocate_manuscript_reference(db)
        db.commit()
        assert db.get(ManuscriptReferenceCounter, "manuscript").value == (
            MAX_REFERENCE_NUMBER
        )


@pytest.mark.parametrize(
    ("references", "last_number"),
    [
        ([], 0),
        (
            [
                "NSH-000010",
                "OTHER-000420",
                "NSAJ-DRAFT-ABC12345",
                "NSAJ-DEADBEEF",
                "NSH-9999999999999999",
            ],
            420,
        ),
    ],
)
def test_actual_migration_seeds_above_existing_ids_and_preserves_references(
    isolated_paper_schema: PostgresCase,
    references: list[str],
    last_number: int,
) -> None:
    engine, schema, submissions = isolated_paper_schema
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic/versions/8e5d7a3c9b10_stable_paper_references.py"
    )
    spec = spec_from_file_location("paper_reference_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "8e5d7a3c9b10"
    with engine.begin() as connection:
        if references:
            connection.execute(
                insert(submissions), [{"reference": value} for value in references]
            )
        ManuscriptReferenceCounter.__table__.drop(connection)
        # The migration contains a raw SQL seed query; constrain its search path
        # to this fixture's unique schema as well as translating ORM table names.
        connection.execute(
            text("SELECT set_config('search_path', :schema, true)"),
            {"schema": schema},
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert set(connection.scalars(select(submissions.c.reference))) == set(
            references
        )
    with Session(engine) as db, db.begin():
        counter = db.get(ManuscriptReferenceCounter, "manuscript")
        assert counter is not None and counter.value == last_number
        assert_random_reference(allocate_manuscript_reference(db))
