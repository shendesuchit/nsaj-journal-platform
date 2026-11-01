from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory


def test_migration_graph_has_single_head() -> None:
    root = Path(__file__).parents[1]
    config = Config(str(root / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)

    heads = scripts.get_heads()
    assert len(heads) == 1, f"Expected one Alembic head, found: {heads}"


def _load_migration():
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "3d4b9f6a2e71_publication_display_order.py"
    )
    spec = importlib.util.spec_from_file_location("publication_order_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backfill_preserves_current_volume_and_issue_order() -> None:
    migration = _load_migration()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    volumes = sa.Table(
        "volumes",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    issues = sa.Table(
        "issues",
        metadata,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("volume_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(50), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    metadata.create_all(engine)

    older_volume = uuid.uuid4()
    newest_volume = uuid.uuid4()
    middle_volume = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            volumes.insert(),
            [
                {"id": older_volume, "year": 2024, "number": 5},
                {"id": newest_volume, "year": 2026, "number": 1},
                {"id": middle_volume, "year": 2025, "number": 2},
            ],
        )
        issue_ids = {number: uuid.uuid4() for number in ("10", "2", "A", "1")}
        connection.execute(
            issues.insert(),
            [
                {"id": issue_ids[number], "volume_id": newest_volume, "number": number}
                for number in ("10", "2", "A", "1")
            ],
        )
        migration._backfill_order(connection)

        volume_order = connection.execute(
            sa.select(volumes.c.id).order_by(volumes.c.display_order)
        ).scalars().all()
        issue_order = connection.execute(
            sa.select(issues.c.number)
            .where(issues.c.volume_id == newest_volume)
            .order_by(issues.c.display_order)
        ).scalars().all()

    assert volume_order == [newest_volume, middle_volume, older_volume]
    assert issue_order == ["1", "2", "10", "A"]
