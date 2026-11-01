"""add manuscript discipline

Revision ID: b72d19a4c8e1
Revises: a91cf2d4e7b6
"""
from collections.abc import Sequence
from alembic import op
import sqlalchemy as sa

revision: str = "b72d19a4c8e1"
down_revision: str | Sequence[str] | None = "a91cf2d4e7b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("discipline", sa.String(length=30), nullable=True))
    op.add_column("articles", sa.Column("discipline", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("articles", "discipline")
    op.drop_column("submissions", "discipline")
