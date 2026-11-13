import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.signing_link import SigningLink
from tests.support import api_routes, authenticate
from tests.test_certificate import _PNG
from tests.test_portal import _auth, _ready, _token

_TINY_PDF = b"%PDF-1.1\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("QUEUE_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    from app.db.session import reset_db

    get_settings.cache_clear()
    reset_db()
    from app.main import app

    with TestClient(app) as test_client:
        authenticate(test_client)
        yield test_client
    reset_db()
    get_settings.cache_clear()


def _snapshot(client: TestClient, case_id: str) -> dict:
    body = client.get(f"/cases/{case_id}").json()
    record = body["case"]
    return {
        "status": record["status"],
        "field_values": body["field_values"],
        "document_count": record["document_count"],
        "updated_at": record["updated_at"],
    }


def test_another_organization_gets_404_and_changes_nothing(client: TestClient, tmp_path: Path) -> None:
    case_id, document_ids = _ready(client, tmp_path)
    before = _snapshot(client, case_id)
    other = authenticate(
        client,
        organization="Other office",
        email="other@example.com",
        display_name="Other",
        set_header=False,
    )
    headers = {"Authorization": f"Bearer {other['token']}"}
    calls = [
        ("GET", f"/cases/{case_id}", None, None),
        ("GET", f"/cases/{case_id}/status", None, None),
        ("GET", f"/cases/{case_id}/events", None, None),
        ("POST", f"/cases/{case_id}/chat", {"message": "hello"}, None),
        ("POST", f"/cases/{case_id}/chat/stream", {"message": "hello"}, None),
        ("POST", f"/cases/{case_id}/upload", None, {"files": ("x.pdf", _TINY_PDF, "application/pdf")}),
        ("POST", f"/cases/{case_id}/classify-manual", {"document_id": document_ids[0], "document_type": "id_copy"}, None),
        ("POST", f"/cases/{case_id}/fields", {"key": "full_name", "value": "Changed"}, None),
        ("POST", f"/cases/{case_id}/fill-and-sign", {"signature_png_base64": _PNG, "field_values": {}, "consent": True}, None),
        ("GET", f"/cases/{case_id}/documents/{document_ids[0]}/file", None, None),
        ("DELETE", f"/cases/{case_id}/documents/{document_ids[0]}", None, None),
        ("PUT", f"/cases/{case_id}/documents/{document_ids[0]}/role", {"role": "form"}, None),
        ("GET", f"/cases/{case_id}/documents/{document_ids[0]}/filled-preview", None, None),
        ("GET", f"/cases/{case_id}/documents/{document_ids[0]}/fill-report", None, None),
        ("GET", f"/cases/{case_id}/intake", None, None),
        ("GET", f"/cases/{case_id}/signed-document", None, None),
        ("GET", f"/cases/{case_id}/certificate", None, None),
        ("POST", f"/cases/{case_id}/signing-links", None, None),
        ("GET", f"/cases/{case_id}/signing-link", None, None),
        ("DELETE", f"/cases/{case_id}/signing-link", None, None),
    ]
    for method, path, payload, files in calls:
        response = client.request(method, path, json=payload, files=files, headers=headers)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code} {response.text}"
    assert _snapshot(client, case_id) == before

    # A new case route must be added above, or this fails.
    called = {
        (method, path.replace(case_id, "{case_id}").replace(document_ids[0], "{document_id}"))
        for method, path, _payload, _files in calls
    }
    assert {route for route in api_routes(client) if "{case_id}" in route[1]} == called


def test_own_case_cannot_reach_another_organizations_document(client: TestClient, tmp_path: Path) -> None:
    case_id, document_ids = _ready(client, tmp_path)
    before = _snapshot(client, case_id)
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    own = client.post("/cases", headers=headers, json={"name": "Theirs", "process_key": "onboarding"})
    assert own.status_code == 201, own.text
    own_id = own.json()["id"]
    read = client.get(f"/cases/{own_id}/documents/{document_ids[0]}/file", headers=headers)
    assert read.status_code == 404, read.text
    relabel = client.post(
        f"/cases/{own_id}/classify-manual",
        headers=headers,
        json={"document_id": document_ids[0], "document_type": "id_copy"},
    )
    assert relabel.status_code == 404, relabel.text
    assert _snapshot(client, case_id) == before


def test_case_list_is_limited_to_the_caller(client: TestClient) -> None:
    own = client.post("/cases", json={"name": "Ours", "process_key": "onboarding"})
    assert own.status_code == 201, own.text
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    listed = client.get("/cases", headers={"Authorization": f"Bearer {other['token']}"})
    assert listed.status_code == 200
    assert listed.json() == []
    assert len(client.get("/cases").json()) == 1


def test_portal_flow_without_an_office_session(client: TestClient, tmp_path: Path) -> None:
    staff = client.get("/auth/me").json()
    case_id, _ = _ready(client, tmp_path)
    created = client.post(f"/cases/{case_id}/signing-links")
    assert created.status_code == 201, created.text
    headers = _auth(_token(created.json()["url"]))
    with TestClient(client.app) as fresh:
        view = fresh.get("/portal", headers=headers)
        assert view.status_code == 200, view.text
        preview = fresh.get("/portal/preview", headers=headers)
        assert preview.status_code == 200
        assert preview.content.startswith(b"%PDF")
        field = fresh.post("/portal/fields", headers=headers, json={"key": "full_name", "value": "Dana Cohen"})
        assert field.status_code == 200, field.text
        with fresh.stream("POST", "/portal/chat/stream", headers=headers, json={"message": "hello"}) as stream:
            assert stream.status_code == 200
            body = "".join(stream.iter_text())
        assert "event: workspace" in body
        current = fresh.get("/portal", headers=headers)
        assert current.status_code == 200, current.text
        signed = fresh.post(
            "/portal/sign",
            headers=headers,
            json={"signature_png_base64": _PNG, "review_digest": current.json()["review_digest"], "consent": True},
        )
        assert signed.status_code == 200, signed.text
        download = fresh.get("/portal/signed-document", headers=headers)
        assert download.status_code == 200
        assert download.content.startswith(b"%PDF")

    async def actors() -> list[tuple[str, str]]:
        async with session_scope() as session:
            rows = (await session.scalars(select(AuditLog).order_by(AuditLog.created_at))).all()
            return [(row.action, row.actor) for row in rows]

    recorded = client.portal.call(actors)
    assert ("signing_link_created", f"user:{staff['id']}") in recorded
    assert ("fill_and_sign", "signer") in recorded


def test_revoked_and_expired_links_fail_and_office_signing_closes_a_link(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    created = client.post(f"/cases/{case_id}/signing-links")
    assert created.status_code == 201, created.text
    token = _token(created.json()["url"])

    async def expire() -> None:
        from app.services.portal_service import hash_token

        async with session_scope() as session:
            link = await session.scalar(select(SigningLink).where(SigningLink.token_hash == hash_token(token)))
            assert link is not None
            link.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()

    client.portal.call(expire)
    assert client.get("/portal", headers=_auth(token)).status_code == 410
    replacement = client.post(f"/cases/{case_id}/signing-links")
    revoked_token = _token(replacement.json()["url"])
    assert client.delete(f"/cases/{case_id}/signing-link").status_code == 204
    assert client.get("/portal", headers=_auth(revoked_token)).status_code == 410
    open_link = client.post(f"/cases/{case_id}/signing-links")
    open_token = _token(open_link.json()["url"])
    view = client.get(f"/cases/{case_id}")
    signed = client.post(
        f"/cases/{case_id}/fill-and-sign",
        json={"signature_png_base64": _PNG, "field_values": {}, "consent": True},
    )
    assert signed.status_code == 200, signed.text
    assert client.get("/portal", headers=_auth(open_token)).status_code == 410
    assert view.status_code == 200


def test_office_certificate_records_proxy_client_headers(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    signed = client.post(
        f"/cases/{case_id}/fill-and-sign",
        headers={"X-Office-Client-Ip": "203.0.113.9", "X-Office-User-Agent": "OfficeBrowser/9"},
        json={"signature_png_base64": _PNG, "field_values": {}, "consent": True},
    )
    assert signed.status_code == 200, signed.text
    certificate = signed.json()["case"]["audit"]["certificate"]
    assert certificate["signer_ip"] == "203.0.113.9"
    assert certificate["signer_user_agent"] == "OfficeBrowser/9"


def test_learning_search_requires_the_organization_filter() -> None:
    from types import SimpleNamespace
    from uuid import UUID

    from app.services.learning_store import QdrantLearningStore

    ours = UUID("11111111-1111-1111-1111-111111111111")

    class Point:
        def __init__(self, organization_id: str | None) -> None:
            self.payload = {"document_type": "id_document", "excerpt": "passport"}
            if organization_id is not None:
                self.payload["organization_id"] = organization_id
            self.score = 0.9

    class Stub:
        def __init__(self) -> None:
            self.kwargs: dict = {}

        def collection_exists(self, collection_name: str) -> bool:
            return True

        def query_points(self, **kwargs):
            self.kwargs = kwargs
            return type("Result", (), {"points": [Point(str(ours)), Point(str(uuid4())), Point(None)]})()

    store = QdrantLearningStore(SimpleNamespace(), None)  # type: ignore[arg-type]
    stub = Stub()
    store._client = stub
    found = store._search([0.1, 0.2], 3, ours)
    assert len(found) == 1
    assert found[0].document_type == "id_document"
    condition = stub.kwargs["query_filter"].must[0]
    assert condition.key == "organization_id"
    assert condition.match.value == str(ours)


def test_worker_processes_a_case_outside_the_default_organization(client: TestClient) -> None:
    from app.workers.runner import process_case_job

    created = client.post("/cases", json={"name": "Branch case", "process_key": "onboarding"})
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]

    async def run() -> str:
        await process_case_job(UUID(case_id), client.app.state.container)
        async with session_scope() as session:
            case = await session.get(Case, UUID(case_id))
            assert case is not None
            return str(case.organization_id)

    organization_id = client.portal.call(run)
    assert organization_id == client.get("/auth/me").json()["organization_id"]
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    hidden = client.get(f"/cases/{case_id}", headers={"Authorization": f"Bearer {other['token']}"})
    assert hidden.status_code == 404


def _alembic(database: Path, revision: str) -> None:
    root = Path(__file__).resolve().parents[1]
    env = {**__import__("os").environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database.as_posix()}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        cwd=root,
        env=env,
        check=True,
    )


def _insert_legacy_case(database: Path) -> None:
    connection = sqlite3.connect(database)
    process_id = uuid4().hex
    now = "2026-01-01 00:00:00"
    connection.execute(
        """
        INSERT INTO process_definitions (
            id, key, name, description, required_documents, optional_documents,
            required_fields, template_filename, layout, created_at, updated_at
        ) VALUES (?, 'onboarding', 'Employee onboarding', 'Pack', '[]', '[]', '[]', 'onboarding-v1.pdf', '{}', ?, ?)
        """,
        (process_id, now, now),
    )
    connection.execute(
        """
        INSERT INTO cases (id, name, process_definition_id, status, field_values, chat_history, created_at, updated_at)
        VALUES (?, 'Legacy', ?, 'draft', '{}', '[]', ?, ?)
        """,
        (uuid4().hex, process_id, now, now),
    )
    connection.commit()
    connection.close()


def test_migration_assigns_existing_cases_to_the_default_organization(tmp_path: Path) -> None:
    database = tmp_path / "legacy.db"
    _alembic(database, "20261106_0005")
    _insert_legacy_case(database)
    _alembic(database, "head")
    connection = sqlite3.connect(database)
    row = connection.execute(
        """
        SELECT organizations.name FROM cases
        JOIN organizations ON organizations.id = cases.organization_id
        """
    ).fetchone()
    connection.close()
    assert row == ("Default organization",)


def test_boot_backfill_assigns_existing_cases_to_the_default_organization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    database = tmp_path / "boot.db"
    _alembic(database, "20261106_0005")
    _insert_legacy_case(database)
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{database.as_posix()}")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    get_settings.cache_clear()
    from app.db.base import Base
    from app.db.compat import ensure_case_columns, ensure_default_organization
    from app.db.session import get_engine, reset_db

    reset_db()

    async def boot() -> None:
        async with get_engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        await ensure_case_columns()
        await ensure_default_organization()

    import asyncio

    asyncio.run(boot())
    connection = sqlite3.connect(database)
    row = connection.execute(
        """
        SELECT organizations.name FROM cases
        JOIN organizations ON organizations.id = cases.organization_id
        """
    ).fetchone()
    connection.close()
    reset_db()
    get_settings.cache_clear()
    assert row == ("Default organization",)
