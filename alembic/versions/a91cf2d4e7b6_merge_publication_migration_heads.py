"""merge publication ordering and stable reference migration heads

Revision ID: a91cf2d4e7b6
Revises: 3d4b9f6a2e71, 8e5d7a3c9b10
Create Date: 2026-10-24 00:00:00.000000

"""

from collections.abc import Sequence

revision: str = "a91cf2d4e7b6"
down_revision: str | Sequence[str] | None = ("3d4b9f6a2e71", "8e5d7a3c9b10")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
