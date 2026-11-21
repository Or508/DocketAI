"""A database built by Alembic alone must match the models, so production never depends on start-up patches."""

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]


def _alembic(database: Path, *args: str) -> None:
    env = {**__import__("os").environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database.as_posix()}"}
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, check=True, capture_output=True)


def _differences(database: Path) -> list:
    from app.db.base import Base
    import app.models  # noqa: F401

    engine = create_engine(f"sqlite:///{database.as_posix()}")
    try:
        with engine.connect() as connection:
            found = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    finally:
        engine.dispose()
    # SQLite reports the signing link's unique token as an index rather than a constraint. Same rule either way.
    return [
        item for item in found
        if not (isinstance(item, tuple) and item[0] in {"remove_index", "add_constraint"} and "signing_links" in str(item[1]))
    ]


def test_alembic_head_matches_the_models(tmp_path: Path) -> None:
    database = tmp_path / "fresh.db"
    _alembic(database, "upgrade", "head")
    assert _differences(database) == []


def test_users_from_before_roles_become_owners(tmp_path: Path) -> None:
    database = tmp_path / "old.db"
    _alembic(database, "upgrade", "20261111_0009")
    connection = sqlite3.connect(database)
    connection.execute("INSERT INTO organizations (id, name, created_at) VALUES ('o1', 'Office', '2026-01-01')")
    connection.execute(
        "INSERT INTO users (id, organization_id, email, password_hash, display_name, is_active, failed_logins, created_at)"
        " VALUES ('u1', 'o1', 'a@example.com', 'x', 'A', 1, 0, '2026-01-01')"
    )
    connection.commit()
    connection.close()
    _alembic(database, "upgrade", "head")
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT role FROM users").fetchone() == ("owner",)
    connection.close()


@pytest.mark.parametrize("target", ["20261111_0009"])
def test_the_new_migration_downgrades(tmp_path: Path, target: str) -> None:
    database = tmp_path / "down.db"
    _alembic(database, "upgrade", "head")
    _alembic(database, "downgrade", target)
    connection = sqlite3.connect(database)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    connection.close()
    assert "account_tokens" not in tables and "role" not in columns
