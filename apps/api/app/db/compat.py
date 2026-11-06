from sqlalchemy import inspect, text

from app.db.session import get_engine

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
