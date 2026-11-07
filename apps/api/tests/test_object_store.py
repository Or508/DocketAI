import asyncio
from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.exceptions import StorageUnavailableError
from app.domain.storage_keys import validate_key
from app.services.object_store import LocalObjectStore, ObjectMissingError, S3ObjectStore

PAYLOAD = b"%PDF-1.4 object-store"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(params=["local", "s3"])
def store(request: pytest.FixtureRequest, tmp_path: Path):
    if request.param == "local":
        yield LocalObjectStore(tmp_path / "root")
        return
    from moto import mock_aws

    with mock_aws():
        import boto3

        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="docketai")
        settings = Settings(
            storage_backend="s3",
            s3_bucket="docketai",
            s3_region="us-east-1",
            s3_endpoint_url="",
            s3_force_path_style=False,
            s3_access_key_id="testing",
            s3_secret_access_key="testing",
        )
        yield S3ObjectStore(settings)


def test_put_get_exists_and_delete(store, tmp_path: Path) -> None:
    key = "org/11111111-1111-1111-1111-111111111111/cases/22222222-2222-2222-2222-222222222222/documents/abc.pdf"
    source = tmp_path / "payload.pdf"
    source.write_bytes(PAYLOAD)

    async def scenario() -> None:
        await store.put_file(key, source, "application/pdf")
        assert await store.get_bytes(key) == PAYLOAD
        assert await store.exists(key) is True
        await store.delete(key)
        assert await store.exists(key) is False
        await store.delete(key)

    _run(scenario())


def test_open_read_and_missing_key(store, tmp_path: Path) -> None:
    key = "org/11111111-1111-1111-1111-111111111111/file.pdf"
    source = tmp_path / "payload.pdf"
    source.write_bytes(PAYLOAD)

    async def scenario() -> None:
        await store.put_file(key, source, "application/pdf")
        reader = await store.open_read(key)
        try:
            assert reader.size == len(PAYLOAD)
            assert b"".join(reader.chunks) == PAYLOAD
        finally:
            reader.close()
        with pytest.raises(ObjectMissingError):
            await store.open_read("org/11111111-1111-1111-1111-111111111111/missing.pdf")

    _run(scenario())


def test_local_copy_keeps_the_suffix_and_is_removed(store, tmp_path: Path) -> None:
    key = "org/11111111-1111-1111-1111-111111111111/packet.pdf"
    source = tmp_path / "payload.pdf"
    source.write_bytes(PAYLOAD)

    async def scenario() -> Path:
        await store.put_file(key, source, "application/pdf")
        async with store.local_copy(key) as path:
            assert path.suffix == ".pdf"
            assert path.read_bytes() == PAYLOAD
            return path

    copied = _run(scenario())
    assert not copied.exists()


def test_validate_key_rejects_unsafe_values() -> None:
    for key in ("", "/abs.pdf", "a\\b.pdf", "C:/drive.pdf", "a/../b.pdf", "a/./b.pdf", "a//b.pdf"):
        with pytest.raises(ValueError):
            validate_key(key)


def test_local_store_refuses_a_key_outside_root(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path / "root")
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(PAYLOAD)
    with pytest.raises(ObjectMissingError):
        _run(store.get_bytes(str(outside)))


def test_s3_put_sends_encryption(tmp_path: Path) -> None:
    from moto import mock_aws

    source = tmp_path / "payload.pdf"
    source.write_bytes(PAYLOAD)
    key = "org/11111111-1111-1111-1111-111111111111/encrypted.pdf"
    with mock_aws():
        import boto3

        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="docketai")
        settings = Settings(
            storage_backend="s3",
            s3_bucket="docketai",
            s3_region="us-east-1",
            s3_access_key_id="testing",
            s3_secret_access_key="testing",
            s3_endpoint_url="",
            s3_force_path_style=False,
            s3_server_side_encryption="aws:kms",
            s3_kms_key_id="alias/docket",
        )
        store = S3ObjectStore(settings)
        seen: dict = {}
        client = store._s3()
        original = client.put_object

        def record(**kwargs):
            seen.update(kwargs)
            return original(**kwargs)

        client.put_object = record
        _run(store.put_file(key, source, "application/pdf"))
    assert seen["ServerSideEncryption"] == "aws:kms"
    assert seen["SSEKMSKeyId"] == "alias/docket"


def test_s3_connection_failure_is_storage_unavailable(tmp_path: Path) -> None:
    from botocore.exceptions import EndpointConnectionError

    source = tmp_path / "payload.pdf"
    source.write_bytes(PAYLOAD)
    settings = Settings(
        storage_backend="s3",
        s3_bucket="docketai",
        s3_region="us-east-1",
        s3_access_key_id="testing",
        s3_secret_access_key="testing",
    )
    store = S3ObjectStore(settings)

    def broken(**kwargs):
        raise EndpointConnectionError(endpoint_url="http://127.0.0.1:9")

    store._s3().put_object = broken
    with pytest.raises(StorageUnavailableError) as caught:
        _run(store.put_file("org/11111111-1111-1111-1111-111111111111/a.pdf", source, "application/pdf"))
    assert "127.0.0.1" not in caught.value.message
