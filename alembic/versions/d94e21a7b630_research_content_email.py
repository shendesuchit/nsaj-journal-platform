"""Research areas, scheduled content revisions, and private email intake."""

import sqlalchemy as sa

from alembic import op

revision = "d94e21a7b630"
down_revision = "b72d19a4c8e1"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("submissions", "articles"):
        op.add_column(
            table, sa.Column("discipline_other", sa.String(200), nullable=True)
        )
    for table in ("calls_for_papers", "announcements"):
        op.add_column(
            table,
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )
    op.create_table(
        "email_intakes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("message_key", sa.String(64), unique=True, nullable=False),
        sa.Column("message_hash", sa.String(64), nullable=False),
        sa.Column("sender_email", sa.String(320), nullable=False),
        sa.Column("sender_name", sa.String(200), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("metadata_fields", sa.JSON(), nullable=False),
        sa.Column("files", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "submission_id", sa.Uuid(), sa.ForeignKey("submissions.id"), unique=True
        ),
    )
    op.create_index("ix_email_intakes_sender_email", "email_intakes", ["sender_email"])
    op.create_table(
        "outbound_mail",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("encrypted", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(200)),
    )
    op.create_index("ix_outbound_mail_status", "outbound_mail", ["status"])


def downgrade():
    op.drop_table("outbound_mail")
    op.drop_table("email_intakes")
    for table in ("announcements", "calls_for_papers"):
        op.drop_column(table, "version")
    for table in ("articles", "submissions"):
        op.drop_column(table, "discipline_other")
