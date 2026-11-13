from sqlalchemy import inspect, select, text

from app.db.session import get_engine, session_scope
from app.models.case import Case
from app.models.organization import Organization

_CASE_COLUMNS = {
    "signer_verification_id": "VARCHAR(40)",
    "content_sha256": "VARCHAR(64)",
    "file_sha256": "VARCHAR(64)",
    "signed_at": "TIMESTAMP WITH TIME ZONE",
    "case_reference": "VARCHAR(20)",
    "data_completed_at": "TIMESTAMP WITH TIME ZONE",
    "content_path": "VARCHAR(1024)",
    "certificate_data": "JSON",
    "pipeline_stage": "VARCHAR(32) DEFAULT 'draft' NOT NULL",
    "pipeline_message": "VARCHAR(240) DEFAULT '' NOT NULL",
    "pipeline_completed": "INTEGER DEFAULT 0 NOT NULL",
    "pipeline_total": "INTEGER DEFAULT 0 NOT NULL",
    "field_sources": "JSON DEFAULT '{}' NOT NULL",
}

_DOCUMENT_COLUMNS = {
    "form_anchors": "JSON",
    "role": "VARCHAR(16) DEFAULT 'evidence' NOT NULL",
    "display_title": "VARCHAR(120)",
    "reading_report": "JSON",
}


async def ensure_case_columns() -> None:
    async with get_engine().begin() as connection:
        await connection.run_sync(_add_missing_case_columns)


def _add_missing_case_columns(sync_conn) -> None:
    tables = inspect(sync_conn).get_table_names()
    if "cases" not in tables:
        return
    existing = {column["name"] for column in inspect(sync_conn).get_columns("cases")}
    for name, ddl in _CASE_COLUMNS.items():
        if name not in existing:
            sync_conn.execute(text(f"ALTER TABLE cases ADD COLUMN {name} {ddl}"))
    if "organization_id" not in existing:
        kind = "UUID" if sync_conn.dialect.name == "postgresql" else "CHAR(32)"
        sync_conn.execute(text(f"ALTER TABLE cases ADD COLUMN organization_id {kind}"))
    if "documents" in tables:
        present = {column["name"] for column in inspect(sync_conn).get_columns("documents")}
        for name, ddl in _DOCUMENT_COLUMNS.items():
            if name not in present:
                sync_conn.execute(text(f"ALTER TABLE documents ADD COLUMN {name} {ddl}"))


async def ensure_default_organization() -> None:
    async with session_scope() as session:
        pending = list(await session.scalars(select(Case).where(Case.organization_id.is_(None))))
        if not pending:
            return
        organization = await session.scalar(
            select(Organization).where(Organization.name == "Default organization")
        )
        if organization is None:
            organization = Organization(name="Default organization")
            session.add(organization)
            await session.flush()
        for case in pending:
            case.organization_id = organization.id
        await session.commit()
