"""Staff accounts, sessions, and organization-owned cases."""

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261106_0006"
down_revision: Union[str, None] = "20261106_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "organizations" not in tables:
        op.create_table(
            "organizations",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(160), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("email", sa.String(320), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("display_name", sa.String(160), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("failed_logins", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_organization_id", "users", ["organization_id"])
    if "user_sessions" not in tables:
        op.create_table(
            "user_sessions",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
            sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    columns = {column["name"] for column in sa.inspect(bind).get_columns("cases")}
    if "organization_id" not in columns:
        op.add_column(
            "cases",
            sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=True),
        )

    cases = sa.table(
        "cases",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("organization_id", sa.Uuid(as_uuid=True)),
    )
    pending = bind.execute(
        sa.select(sa.func.count()).select_from(cases).where(cases.c.organization_id.is_(None))
    ).scalar_one()
    if pending:
        org_id = uuid.uuid4()
        organizations = sa.table(
            "organizations",
            sa.column("id", sa.Uuid(as_uuid=True)),
            sa.column("name", sa.String()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(
            organizations,
            [
                {
                    "id": org_id,
                    "name": "Default organization",
                    "created_at": datetime.now(timezone.utc),
                }
            ],
        )
        op.execute(cases.update().where(cases.c.organization_id.is_(None)).values(organization_id=org_id))

    inspector = sa.inspect(bind)
    foreign_keys = {item["name"] for item in inspector.get_foreign_keys("cases")}
    with op.batch_alter_table("cases") as batch:
        if "fk_cases_organization_id" not in foreign_keys:
            batch.create_foreign_key(
                "fk_cases_organization_id",
                "organizations",
                ["organization_id"],
                ["id"],
            )
        batch.alter_column(
            "organization_id",
            existing_type=sa.Uuid(as_uuid=True),
            nullable=False,
        )
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("cases")}
    if "ix_cases_organization_id" not in indexes:
        op.create_index("ix_cases_organization_id", "cases", ["organization_id"])


def downgrade() -> None:
    op.drop_index("ix_cases_organization_id", table_name="cases")
    with op.batch_alter_table("cases") as batch:
        batch.drop_constraint("fk_cases_organization_id", type_="foreignkey")
        batch.drop_column("organization_id")
    op.drop_index("ix_user_sessions_user_id", table_name="user_sessions")
    op.drop_table("user_sessions")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_table("users")
    op.drop_table("organizations")
