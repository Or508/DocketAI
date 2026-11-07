import ast
import asyncio
from pathlib import Path

import pytest

from app.core.config import Settings
from app.domain.storage_keys import document_key
from app.services.storage.local_storage import LocalStorage
from app.services.storage.s3_storage import S3Storage
from uuid import UUID

PAYLOAD = b"%PDF-1.4 storage-service"
ORG = UUID("11111111-1111-1111-1111-111111111111")
CASE = UUID("22222222-2222-2222-2222-222222222222")


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(params=["local", "s3"])
def storage(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "local":
        yield LocalStorage(tmp_path / "root")
        return
    from moto import mock_aws

    with mock_aws():
        import boto3

        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="docket-storage")
        settings = Settings(
            storage_backend="s3",
            s3_bucket="docket-storage",
            s3_region="us-east-1",
            s3_endpoint_url="",
            s3_force_path_style=False,
            s3_access_key_id="minioadmin",
            s3_secret_access_key="minioadmin",
        )
        yield S3Storage(settings)


def test_storage_service_round_trip(storage) -> None:
    key = document_key(ORG, CASE, ".pdf")

    async def scenario() -> None:
        await storage.upload_file(key, PAYLOAD, "application/pdf")
        assert await storage.download_file(key) == PAYLOAD
        assert await storage.get_sha256(key) == __import__("hashlib").sha256(PAYLOAD).hexdigest()
        assert await storage.exists(key) is True
        chunks = bytearray()
        async for chunk in storage.stream_file(key):
            chunks.extend(chunk)
        assert bytes(chunks) == PAYLOAD
        await storage.delete_file(key)
        assert await storage.exists(key) is False

    _run(scenario())


def test_key_has_no_display_name() -> None:
    key = document_key(ORG, CASE, ".pdf")
    assert key == f"org/{ORG}/cases/{CASE}/documents/{key.rsplit('/', 1)[-1]}"
    assert "Dana" not in key
    assert "onboarding" not in key


def test_case_service_does_not_import_boto3() -> None:
    path = Path(__file__).resolve().parents[1] / "app" / "services" / "case_service.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name != "boto3" and not alias.name.startswith("boto3.") for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "boto3"


def test_invalidation_does_not_delete_the_stored_object(storage) -> None:
    key = document_key(ORG, CASE, ".pdf")
    source = Path(__file__).resolve().parents[1] / "app" / "services" / "case_service.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    invalidate = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CaseService"
        for node in node.body
        if isinstance(node, ast.FunctionDef) and node.name == "_invalidate_signature"
    )
    calls = [
        node.func.attr
        for node in ast.walk(invalidate)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]
    assert "delete" not in calls
    assert "delete_file" not in calls

    async def scenario() -> None:
        await storage.upload_file(key, PAYLOAD, "application/pdf")
        assert await storage.exists(key) is True

    _run(scenario())


def test_altered_bytes_change_the_sha256(storage) -> None:
    key = document_key(ORG, CASE, ".pdf")

    async def scenario() -> None:
        await storage.upload_file(key, PAYLOAD, "application/pdf")
        original = await storage.get_sha256(key)
        await storage.upload_file(key, b"%PDF-1.4 tampered", "application/pdf")
        assert await storage.get_sha256(key) != original

    _run(scenario())
