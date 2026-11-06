"""Store the certificate of completion on a signed case."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261106_0005"
down_revision: Union[str, None] = "20261106_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("cases")}
    if "case_reference" not in columns:
        op.add_column("cases", sa.Column("case_reference", sa.String(length=20), nullable=True))
    if "data_completed_at" not in columns:
        op.add_column("cases", sa.Column("data_completed_at", sa.DateTime(timezone=True), nullable=True))
    if "content_path" not in columns:
        op.add_column("cases", sa.Column("content_path", sa.String(length=1024), nullable=True))
    if "certificate_data" not in columns:
        op.add_column("cases", sa.Column("certificate_data", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "certificate_data")
    op.drop_column("cases", "content_path")
    op.drop_column("cases", "data_completed_at")
    op.drop_column("cases", "case_reference")
