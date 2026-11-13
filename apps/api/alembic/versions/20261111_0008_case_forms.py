"""Mark office AcroForms and store the title shown in provenance."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261111_0008"
down_revision: Union[str, None] = "20261110_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    documents = {column["name"] for column in inspector.get_columns("documents")}
    if "role" not in documents:
        op.add_column(
            "documents",
            sa.Column("role", sa.String(length=16), nullable=False, server_default="evidence"),
        )
    if "display_title" not in documents:
        op.add_column("documents", sa.Column("display_title", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "display_title")
    op.drop_column("documents", "role")
