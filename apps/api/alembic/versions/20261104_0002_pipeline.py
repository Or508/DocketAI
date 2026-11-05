"""Case pipeline progress and signature audit columns."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261104_0002"
down_revision: Union[str, None] = "20261104_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cases", sa.Column("signer_verification_id", sa.String(40), nullable=True))
    op.add_column("cases", sa.Column("content_sha256", sa.String(64), nullable=True))
    op.add_column(
        "cases",
        sa.Column("pipeline_stage", sa.String(32), nullable=False, server_default="draft"),
    )
    op.add_column(
        "cases",
        sa.Column("pipeline_message", sa.String(240), nullable=False, server_default=""),
    )
    op.add_column(
        "cases",
        sa.Column("pipeline_completed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "cases",
        sa.Column("pipeline_total", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("cases", "pipeline_total")
    op.drop_column("cases", "pipeline_completed")
    op.drop_column("cases", "pipeline_message")
    op.drop_column("cases", "pipeline_stage")
    op.drop_column("cases", "content_sha256")
    op.drop_column("cases", "signer_verification_id")
