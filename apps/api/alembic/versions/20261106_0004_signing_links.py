"""Signer magic links."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261106_0004"
down_revision: Union[str, None] = "20261105_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OPEN = sa.text("revoked_at IS NULL AND completed_at IS NULL")


def upgrade() -> None:
    bind = op.get_bind()
    if "signing_links" in sa.inspect(bind).get_table_names():
        return
    op.create_table(
        "signing_links",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("case_id", sa.Uuid(as_uuid=True), sa.ForeignKey("cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=64), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("download_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signed_file_sha256", sa.String(length=64), nullable=True),
        sa.Column("chat_turns", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_signing_links_case_id", "signing_links", ["case_id"])
    op.create_index("ix_signing_links_token_hash", "signing_links", ["token_hash"], unique=True)
    op.create_index(
        "uq_signing_links_one_open",
        "signing_links",
        ["case_id"],
        unique=True,
        sqlite_where=_OPEN,
        postgresql_where=_OPEN,
    )


def downgrade() -> None:
    op.drop_index("uq_signing_links_one_open", table_name="signing_links")
    op.drop_index("ix_signing_links_token_hash", table_name="signing_links")
    op.drop_index("ix_signing_links_case_id", table_name="signing_links")
    op.drop_table("signing_links")
