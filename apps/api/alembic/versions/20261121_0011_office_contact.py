"""How a client reaches the office: a phone and an email shown on the client's pages."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261121_0011"
down_revision: Union[str, None] = "20261121_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    present = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("organizations")}
    if "contact_phone" not in present:
        op.add_column("organizations", sa.Column("contact_phone", sa.String(40), nullable=True))
    if "contact_email" not in present:
        op.add_column("organizations", sa.Column("contact_email", sa.String(320), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("contact_email")
        batch.drop_column("contact_phone")
