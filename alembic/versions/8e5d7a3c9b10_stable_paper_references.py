"""Add atomic allocation of stable paper references.

Revision ID: 8e5d7a3c9b10
Revises: c16b52ef7f13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "8e5d7a3c9b10"
down_revision: str | Sequence[str] | None = "c16b52ef7f13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "manuscript_reference_counters",
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "value >= 0 AND value <= 999999999999999",
            name="ck_manuscript_reference_counters_value",
        ),
        sa.PrimaryKeyConstraint("name"),
    )
    # Preserve legacy references. Start above any existing numeric paper ID so
    # installing the allocator cannot collide with a previously issued number.
    op.execute(
        sa.text(
            "INSERT INTO manuscript_reference_counters (name, value) "
            "SELECT 'manuscript', COALESCE(MAX("
            "SUBSTRING(reference FROM '[0-9]+$')::bigint), 0) "
            "FROM submissions "
            "WHERE reference ~ '^[A-Z][A-Z0-9]{0,7}-[0-9]{1,15}$'"
        )
    )


def downgrade() -> None:
    raise RuntimeError("Downgrade disabled: preserve paper ID allocation history.")
