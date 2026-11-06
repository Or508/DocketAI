"""Store the downloaded-file hash and the time the packet was signed."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261105_0003"
down_revision: Union[str, None] = "20261104_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("cases")}
    if "file_sha256" not in columns:
        op.add_column("cases", sa.Column("file_sha256", sa.String(length=64), nullable=True))
    if "signed_at" not in columns:
        op.add_column("cases", sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("cases", "signed_at")
    op.drop_column("cases", "file_sha256")
