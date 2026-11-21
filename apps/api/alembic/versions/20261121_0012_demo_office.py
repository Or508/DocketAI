"""A public demo office expires, and cleanup deletes only those rows."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261121_0012"
down_revision: Union[str, None] = "20261121_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    present = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("organizations")}
    if "demo_expires_at" not in present:
        op.add_column("organizations", sa.Column("demo_expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("demo_expires_at")
