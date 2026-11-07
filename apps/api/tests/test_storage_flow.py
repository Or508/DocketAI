import ast
import base64
import hashlib
from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import StorageUnavailableError
from app.db.session import session_scope
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.document import Document
from app.services.storage_migration import migrate_storage
from tests.test_certificate import _PNG, _ready

_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Count 1 /Kids [3 0 R] >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj\n"
    b"trailer << /Root 1 0 R >>\n%%EOF\n"
)
_PNG_BYTES = base64.b64decode(_PNG)
_FAILURE = {
    "detail": "File storage is unavailable. Try again shortly.",
    "code": "storage_unavailable",
}


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
        from tests.support import authenticate

        authenticate(test_client)
        yield test_client
    reset_db()
    get_settings.cache_clear()


def _sign(client: TestClient, case_id: str):
    response = client.post(
        f"/cases/{case_id}/fill-and-sign",
        json={"signature_png_base64": _PNG, "field_values": {}, "consent": True},
    )
    assert response.status_code == 200, response.text
    return response


async def _case(case_id: str) -> Case:
    async with session_scope() as session:
        case = await session.scalar(
            select(Case).where(Case.id == UUID(case_id)).options(selectinload(Case.documents))
        )
        assert case is not None
        return case


def test_new_keys_are_organization_scoped_and_omit_the_case_name(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="SECRET-CASE-NAME", client_name="Dana")
    _sign(client, case_id)
    stored = client.portal.call(_case, case_id)
    org = str(stored.organization_id)
    prefix = f"org/{org}/cases/{case_id}/"
    assert stored.output_path is not None and stored.content_path is not None
    assert stored.output_path.startswith(prefix)
    assert stored.content_path.startswith(prefix)
    assert "SECRET-CASE-NAME" not in stored.output_path
    assert "SECRET-CASE-NAME" not in stored.content_path
    for document in stored.documents:
        assert document.storage_path.startswith(prefix + "documents/")
        assert "SECRET-CASE-NAME" not in document.storage_path
        assert document.original_filename not in document.storage_path


def test_invalidation_retains_objects_and_a_second_signature_gets_new_keys(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Retain", client_name="Dana")
    _sign(client, case_id)
    first = client.portal.call(_case, case_id)
    packet = client.portal.call(client.app.state.container.store.get_bytes, first.output_path)
    form = client.portal.call(client.app.state.container.store.get_bytes, first.content_path)
    changed = client.post(f"/cases/{case_id}/fields", json={"key": "full_name", "value": "Noa Levi"})
    assert changed.status_code == 200, changed.text
    cleared = client.portal.call(_case, case_id)
    assert cleared.output_path is None
    assert cleared.content_path is None
    assert client.portal.call(client.app.state.container.store.get_bytes, first.output_path) == packet
    assert client.portal.call(client.app.state.container.store.get_bytes, first.content_path) == form

    async def audit() -> dict:
        async with session_scope() as session:
            row = await session.scalar(
                select(AuditLog).where(AuditLog.case_id == UUID(case_id)).order_by(AuditLog.created_at.desc())
            )
            assert row is not None and row.previous_value is not None
            return row.previous_value

    previous = client.portal.call(audit)
    assert previous["output_path"] == first.output_path
    assert previous["content_path"] == first.content_path
    _sign(client, case_id)
    second = client.portal.call(_case, case_id)
    assert second.output_path != first.output_path
    assert client.portal.call(client.app.state.container.store.get_bytes, first.output_path) == packet


def test_failed_upload_commit_leaves_the_signed_packet(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Commit", client_name="Dana")
    _sign(client, case_id)
    stored = client.portal.call(_case, case_id)
    packet = client.portal.call(client.app.state.container.store.get_bytes, stored.output_path)
    original = AsyncSession.commit

    async def fail(self):
        raise RuntimeError("commit failed")

    AsyncSession.commit = fail
    try:
        with pytest.raises(RuntimeError):
            client.post(
                f"/cases/{case_id}/upload",
                files={"files": ("extra.pdf", _PDF, "application/pdf")},
            )
    finally:
        AsyncSession.commit = original
    assert client.portal.call(client.app.state.container.store.get_bytes, stored.output_path) == packet
    again = client.portal.call(_case, case_id)
    assert again.output_path == stored.output_path
    assert len(again.documents) == len(stored.documents)


def test_failed_put_during_upload_leaves_no_document_or_object(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Put", client_name="Dana")
    before = client.portal.call(_case, case_id)
    keys = {document.storage_path for document in before.documents}

    async def fail(key, path, content_type):
        raise RuntimeError("put failed")

    client.app.state.container.store.put_file = fail
    with pytest.raises(RuntimeError):
        client.post(f"/cases/{case_id}/upload", files={"files": ("extra.pdf", _PDF, "application/pdf")})
    after = client.portal.call(_case, case_id)
    assert {document.storage_path for document in after.documents} == keys
    assert len(after.documents) == len(before.documents)


def test_failed_put_during_signing_leaves_the_case_unsigned(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Unsigned", client_name="Dana")
    created = client.post(f"/cases/{case_id}/signing-links")
    assert created.status_code == 201, created.text
    token = created.json()["url"].rstrip("/").rsplit("/", 1)[-1]
    root = tmp_path / "storage"
    before = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}

    async def fail(key, path, content_type):
        raise RuntimeError("put failed")

    client.app.state.container.store.put_file = fail
    with pytest.raises(RuntimeError):
        client.post(
            "/portal/sign",
            headers={"Authorization": f"Bearer {token}"},
            json={"signature_png_base64": _PNG, "review_digest": client.get("/portal", headers={"Authorization": f"Bearer {token}"}).json()["review_digest"], "consent": True},
        )
    after = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    assert after == before
    opened = client.get("/portal", headers={"Authorization": f"Bearer {token}"})
    assert opened.status_code == 200
    assert opened.json()["state"] == "open"
    assert client.get(f"/cases/{case_id}").json()["case"]["status"] != "signed"


@pytest.mark.local_storage
def test_failed_signing_commit_keeps_the_objects(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Keep", client_name="Dana")
    root = tmp_path / "storage"
    before = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    original = AsyncSession.commit

    async def fail(self):
        raise RuntimeError("commit failed")

    AsyncSession.commit = fail
    try:
        with pytest.raises(RuntimeError):
            _sign(client, case_id)
    finally:
        AsyncSession.commit = original
    after = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    created = after - before
    assert created
    assert any(path.endswith("/signed.pdf") for path in created)
    assert client.get(f"/cases/{case_id}").json()["case"]["status"] != "signed"


def test_tampered_signed_file_fails_the_integrity_check(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Tamper", client_name="Dana")
    created = client.post(f"/cases/{case_id}/signing-links")
    token = created.json()["url"].rstrip("/").rsplit("/", 1)[-1]
    view = client.get("/portal", headers={"Authorization": f"Bearer {token}"})
    signed = client.post(
        "/portal/sign",
        headers={"Authorization": f"Bearer {token}"},
        json={"signature_png_base64": _PNG, "review_digest": view.json()["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    stored = client.portal.call(_case, case_id)
    # Overwrite through the configured store so this also runs against S3.
    tampered = tmp_path / "tampered.pdf"
    tampered.write_bytes(b"%PDF-1.4 tampered")
    client.portal.call(client.app.state.container.store.put_file, stored.output_path, tampered, "application/pdf")
    for path in (
        f"/cases/{case_id}/signed-document",
        f"/cases/{case_id}/certificate",
    ):
        response = client.get(path)
        assert response.status_code == 500, response.text
        assert response.json()["code"] == "integrity_failed"
    portal = client.get("/portal/signed-document", headers={"Authorization": f"Bearer {token}"})
    assert portal.status_code == 500, portal.text
    assert portal.json()["code"] == "integrity_failed"


def test_missing_objects_are_not_found(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Missing", client_name="Dana")
    created = client.post(f"/cases/{case_id}/signing-links")
    token = created.json()["url"].rstrip("/").rsplit("/", 1)[-1]
    view = client.get("/portal", headers={"Authorization": f"Bearer {token}"})
    signed = client.post(
        "/portal/sign",
        headers={"Authorization": f"Bearer {token}"},
        json={"signature_png_base64": _PNG, "review_digest": view.json()["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    stored = client.portal.call(_case, case_id)
    document_id = stored.documents[0].id
    missing = f"org/{stored.organization_id}/cases/{case_id}/signed/missing/signed.pdf"

    async def retarget() -> None:
        async with session_scope() as session:
            case = await session.get(Case, UUID(case_id))
            assert case is not None
            case.output_path = missing
            case.documents[0].storage_path = f"org/{stored.organization_id}/cases/{case_id}/documents/missing.pdf"
            await session.commit()

    client.portal.call(retarget)
    assert client.get(f"/cases/{case_id}/documents/{document_id}/file").status_code == 404
    assert client.get(f"/cases/{case_id}/signed-document").status_code == 404
    assert client.get(f"/cases/{case_id}/certificate").status_code == 404
    assert client.get("/portal/signed-document", headers={"Authorization": f"Bearer {token}"}).status_code == 404


def test_storage_failure_hides_internal_detail(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Down", client_name="Dana")
    _sign(client, case_id)

    async def fail(key: str) -> bytes:
        raise StorageUnavailableError()

    client.app.state.container.store.get_bytes = fail
    response = client.get(f"/cases/{case_id}/signed-document")
    assert response.status_code == 503
    assert response.json() == _FAILURE
    assert "Traceback" not in response.text


def test_hebrew_filename_is_encoded_in_content_disposition(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Hebrew", client_name="Dana")
    uploaded = client.post(
        f"/cases/{case_id}/upload",
        files={"files": ("תעודה.pdf", _PDF, "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    stored = client.portal.call(_case, case_id)
    document = next(item for item in stored.documents if item.original_filename == "תעודה.pdf")
    response = client.get(f"/cases/{case_id}/documents/{document.id}/file")
    assert response.status_code == 200, response.text
    disposition = response.headers["content-disposition"]
    assert "filename*=utf-8''" in disposition
    assert "%D7%AA" in disposition


def test_image_upload_is_processed_through_local_copy(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Image", client_name="Dana")
    uploaded = client.post(
        f"/cases/{case_id}/upload",
        files={"files": ("scan.png", _PNG_BYTES, "image/png")},
    )
    assert uploaded.status_code == 200, uploaded.text
    stored = client.portal.call(_case, case_id)
    image = next(item for item in stored.documents if item.original_filename == "scan.png")
    assert image.status != "uploaded"
    assert image.storage_path.endswith(".png")


@pytest.mark.local_storage
def test_existing_relative_keys_still_download(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Legacy", client_name="Dana")
    stored = client.portal.call(_case, case_id)
    document = stored.documents[0]
    relative = f"cases/{case_id}/legacy.pdf"
    destination = tmp_path / "storage" / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = client.portal.call(client.app.state.container.store.get_bytes, document.storage_path)
    destination.write_bytes(payload)

    async def retarget() -> None:
        async with session_scope() as session:
            row = await session.get(Document, document.id)
            assert row is not None
            row.storage_path = relative
            await session.commit()

    client.portal.call(retarget)
    response = client.get(f"/cases/{case_id}/documents/{document.id}/file")
    assert response.status_code == 200
    assert response.content == payload


def test_health_reports_storage(client: TestClient) -> None:
    healthy = client.get("/health")
    assert healthy.status_code == 200
    assert healthy.json()["storage"] == "ok"
    assert healthy.json()["status"] == "ok"

    async def fail() -> None:
        raise StorageUnavailableError()

    client.app.state.container.store.check = fail
    degraded = client.get("/health")
    assert degraded.json()["storage"] == "unavailable"
    assert degraded.json()["status"] == "degraded"


def test_migrate_storage_moves_legacy_keys(client: TestClient, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from moto import mock_aws

    case_id = _ready(client, tmp_path, name="Migrate", client_name="Dana")
    _sign(client, case_id)
    stored = client.portal.call(_case, case_id)
    root = tmp_path / "storage"
    legacy_doc = f"cases/{case_id}/legacy.pdf"
    legacy_packet = f"cases/{case_id}/packet.pdf"
    legacy_form = f"cases/{case_id}/form.pdf"
    packet = client.portal.call(client.app.state.container.store.get_bytes, stored.output_path)
    form = client.portal.call(client.app.state.container.store.get_bytes, stored.content_path)
    document_bytes = client.portal.call(client.app.state.container.store.get_bytes, stored.documents[0].storage_path)
    for relative, payload in ((legacy_doc, document_bytes), (legacy_packet, packet), (legacy_form, form)):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)

    async def point_at_legacy() -> str:
        async with session_scope() as session:
            case = await session.get(Case, UUID(case_id))
            assert case is not None
            case.documents[0].storage_path = legacy_doc
            case.output_path = legacy_packet
            case.content_path = legacy_form
            await session.commit()
            return str(case.organization_id)

    organization_id = client.portal.call(point_at_legacy)
    settings = get_settings()
    settings.storage_backend = "s3"
    settings.s3_bucket = "docketai"
    settings.s3_region = "us-east-1"
    settings.s3_access_key_id = "testing"
    settings.s3_secret_access_key = "testing"
    settings.s3_endpoint_url = ""
    settings.s3_force_path_style = False
    with mock_aws():
        import boto3

        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="docketai")

        async def migrate(dry_run: bool) -> int:
            return await migrate_storage(dry_run=dry_run)

        assert client.portal.call(migrate, False) == 0
        moved = client.portal.call(_case, case_id)
        assert moved.output_path == f"org/{organization_id}/{legacy_packet}"
        assert moved.content_path == f"org/{organization_id}/{legacy_form}"
        assert moved.documents[0].storage_path == f"org/{organization_id}/{legacy_doc}"
        assert (root / legacy_packet).read_bytes() == packet
        assert client.portal.call(migrate, False) == 0
        second = capsys.readouterr().out
        assert "migrated=0" in second

        async def mismatch() -> None:
            async with session_scope() as session:
                case = await session.get(Case, UUID(case_id))
                assert case is not None
                case.documents[0].storage_path = legacy_doc
                case.documents[0].content_hash = "0" * 64
                await session.commit()

        client.portal.call(mismatch)
        assert client.portal.call(migrate, False) == 1
        unchanged = client.portal.call(_case, case_id)
        assert unchanged.documents[0].storage_path == legacy_doc

        async def restore() -> None:
            async with session_scope() as session:
                case = await session.get(Case, UUID(case_id))
                assert case is not None
                case.documents[0].content_hash = hashlib.sha256(document_bytes).hexdigest()
                await session.commit()

        client.portal.call(restore)
        assert client.portal.call(migrate, True) == 0
        dry = client.portal.call(_case, case_id)
        assert dry.documents[0].storage_path == legacy_doc
        assert (root / legacy_doc).read_bytes() == document_bytes


def test_storage_boundaries_stay_where_the_spec_puts_them() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    boto_files = []
    storage_dir_files = []
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name == "boto3" or alias.name.startswith("boto3.") for alias in node.names):
                    boto_files.append(path)
            if isinstance(node, ast.ImportFrom) and node.module and (
                node.module == "boto3" or node.module.startswith("boto3.")
            ):
                boto_files.append(path)
        if "resolved_storage_dir" in source:
            storage_dir_files.append(path.resolve())
        if path.name == "case_service.py":
            assert ".unlink(" not in source
    assert boto_files == [root / "services" / "object_store.py"]
    allowed = {
        (root / "core" / "config.py").resolve(),
        (root / "main.py").resolve(),
        (root / "services" / "object_store.py").resolve(),
        (root / "services" / "storage_migration.py").resolve(),
    }
    assert set(storage_dir_files) <= allowed
