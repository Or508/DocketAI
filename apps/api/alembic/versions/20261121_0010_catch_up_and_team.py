"""Catch the schema up with what the server added on start-up, and add office roles and account links.

Until now these tables and columns were added only by app/db/compat.py when the API started.
A database built by `alembic upgrade head` alone lacked them. Every step checks first, so this
also runs on a database the server already patched.

Users who existed before roles become owners, so nobody loses what they could do.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261121_0010"
down_revision: Union[str, None] = "20261111_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TIME = sa.DateTime(timezone=True)


def _columns(inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = set(inspector.get_table_names())

    organizations = _columns(inspector, "organizations")
    if "profession" not in organizations:
        op.add_column(
            "organizations",
            sa.Column("profession", sa.String(40), nullable=False, server_default="law"),
        )
    if "ai_reading_enabled" not in organizations:
        op.add_column(
            "organizations",
            sa.Column("ai_reading_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        )

    users = _columns(inspector, "users")
    for column in (
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("mfa_secret", sa.Text(), nullable=True),
        sa.Column("mfa_pending_secret", sa.Text(), nullable=True),
        sa.Column("mfa_last_step", sa.Integer(), nullable=True),
        sa.Column("mfa_recovery_hashes", sa.JSON(), nullable=True),
        sa.Column("role", sa.String(16), nullable=False, server_default="owner"),
    ):
        if column.name not in users:
            op.add_column("users", column)

    if "case_notes" not in tables:
        op.create_table(
            "case_notes",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("author_email", sa.String(320), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", _TIME, nullable=False),
        )
        op.create_index("ix_case_notes_case_id", "case_notes", ["case_id"])

    if "intake_links" not in tables:
        op.create_table(
            "intake_links",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("created_at", _TIME, nullable=False),
            sa.Column("expires_at", _TIME, nullable=True),
            sa.Column("revoked_at", _TIME, nullable=True),
        )
        op.create_index("ix_intake_links_case_id", "intake_links", ["case_id"])
        op.create_index(
            "uq_intake_links_one_open",
            "intake_links",
            ["case_id"],
            unique=True,
            sqlite_where=sa.text("revoked_at IS NULL"),
            postgresql_where=sa.text("revoked_at IS NULL"),
        )

    if "case_outreach" not in tables:
        op.create_table(
            "case_outreach",
            sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("email", sa.String(320), nullable=True),
            sa.Column("phone", sa.String(20), nullable=True),
            sa.Column("purpose", sa.String(16), nullable=True),
            sa.Column("link_id", sa.Uuid(), nullable=True),
            sa.Column("token_sealed", sa.Text(), nullable=True),
            sa.Column("channel", sa.String(16), nullable=True),
            sa.Column("reminders_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("first_sent_at", _TIME, nullable=True),
            sa.Column("reminders_sent", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_reminder_at", _TIME, nullable=True),
            sa.Column("stopped_reason", sa.String(32), nullable=True),
            sa.Column("updated_at", _TIME, nullable=False),
        )
        op.create_index("ix_case_outreach_next_reminder_at", "case_outreach", ["next_reminder_at"])

    if "outbound_messages" not in tables:
        op.create_table(
            "outbound_messages",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("case_id", sa.Uuid(), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
            sa.Column("purpose", sa.String(16), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("channel", sa.String(16), nullable=False),
            sa.Column("recipient", sa.String(320), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("error", sa.String(300), nullable=True),
            sa.Column("actor", sa.String(80), nullable=False),
            sa.Column("created_at", _TIME, nullable=False),
        )
        op.create_index("ix_outbound_messages_case_id", "outbound_messages", ["case_id"])
        op.create_index("ix_outbound_messages_case_created", "outbound_messages", ["case_id", "created_at"])

    if "account_tokens" not in tables:
        op.create_table(
            "account_tokens",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("purpose", sa.String(16), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("created_at", _TIME, nullable=False),
            sa.Column("expires_at", _TIME, nullable=False),
            sa.Column("used_at", _TIME, nullable=True),
        )
        op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_table("account_tokens")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("role")
    # The other tables and columns were in use before this migration (added at start-up), so they stay.
