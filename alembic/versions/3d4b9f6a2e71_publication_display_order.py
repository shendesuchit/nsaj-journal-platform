"""persist editorial order for volumes and issues

Revision ID: 3d4b9f6a2e71
Revises: f8841a7c04dd
Create Date: 2026-10-23 12:00:00.000000

"""

from collections import defaultdict
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

revision: str = "3d4b9f6a2e71"
down_revision: str | Sequence[str] | None = "f8841a7c04dd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _backfill_order(connection: sa.Connection) -> None:
    volumes = sa.table(
        "volumes",
        sa.column("id", sa.Uuid()),
        sa.column("year", sa.Integer()),
        sa.column("number", sa.Integer()),
        sa.column("display_order", sa.Integer()),
    )
    issues = sa.table(
        "issues",
        sa.column("id", sa.Uuid()),
        sa.column("volume_id", sa.Uuid()),
        sa.column("number", sa.String(50)),
        sa.column("display_order", sa.Integer()),
    )

    volume_rows = connection.execute(
        sa.select(volumes.c.id, volumes.c.year, volumes.c.number)
    ).mappings()
    ordered_volumes = sorted(
        volume_rows,
        key=lambda row: (-row["year"], -row["number"], str(row["id"])),
    )
    for position, row in enumerate(ordered_volumes):
        connection.execute(
            sa.update(volumes)
            .where(volumes.c.id == row["id"])
            .values(display_order=position)
        )

    issue_rows = connection.execute(
        sa.select(issues.c.id, issues.c.volume_id, issues.c.number)
    ).mappings()
    by_volume: dict[object, list[dict[str, object]]] = defaultdict(list)
    for row in issue_rows:
        by_volume[row["volume_id"]].append(dict(row))

    for rows in by_volume.values():
        def issue_key(row: dict[str, object]) -> tuple[bool, int | str, str, str]:
            number = str(row["number"])
            numeric = number.isdigit()
            return (
                not numeric,
                int(number) if numeric else number.casefold(),
                number.casefold(),
                str(row["id"]),
            )

        for position, row in enumerate(sorted(rows, key=issue_key)):
            connection.execute(
                sa.update(issues)
                .where(issues.c.id == row["id"])
                .values(display_order=position)
            )


def _backfill_order_offline() -> None:
    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT id, ROW_NUMBER() OVER (
                    ORDER BY year DESC, number DESC, id
                ) - 1 AS position
                FROM volumes
            )
            UPDATE volumes AS target
            SET display_order = ordered.position
            FROM ordered
            WHERE target.id = ordered.id
            """
        )
    )
    op.execute(
        sa.text(
            """
            WITH ordered AS (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY volume_id
                    ORDER BY
                        CASE WHEN number ~ '^[0-9]+$' THEN 0 ELSE 1 END,
                        CASE WHEN number ~ '^[0-9]+$' THEN number::numeric END,
                        lower(number), id
                ) - 1 AS position
                FROM issues
            )
            UPDATE issues AS target
            SET display_order = ordered.position
            FROM ordered
            WHERE target.id = ordered.id
            """
        )
    )


def upgrade() -> None:
    op.add_column(
        "volumes",
        sa.Column(
            "display_order", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.add_column(
        "issues",
        sa.Column(
            "display_order", sa.Integer(), server_default=sa.text("0"), nullable=False
        ),
    )
    if context.is_offline_mode():
        _backfill_order_offline()
    else:
        _backfill_order(op.get_bind())


def downgrade() -> None:
    op.drop_column("issues", "display_order")
    op.drop_column("volumes", "display_order")
