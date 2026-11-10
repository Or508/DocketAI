"""Store AcroForm widget anchors on documents and the source of each field value."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261110_0007"
down_revision: Union[str, None] = "20261106_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    documents = {column["name"] for column in inspector.get_columns("documents")}
    if "form_anchors" not in documents:
        op.add_column("documents", sa.Column("form_anchors", sa.JSON(), nullable=True))
    cases = {column["name"] for column in inspector.get_columns("cases")}
    if "field_sources" not in cases:
        op.add_column(
            "cases",
            sa.Column("field_sources", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        )


def downgrade() -> None:
    op.drop_column("cases", "field_sources")
    op.drop_column("documents", "form_anchors")
