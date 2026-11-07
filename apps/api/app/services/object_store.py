import asyncio
import logging
import os
import shutil
import tempfile
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.core.config import Settings
from app.core.exceptions import StorageUnavailableError
from app.domain.storage_keys import validate_key
from app.services.storage_paths import resolve_stored

logger = logging.getLogger(__name__)

_CHUNK = 1024 * 1024


class ObjectMissingError(Exception):
    pass


@dataclass
class ObjectReader:
    size: int
    chunks: Iterator[bytes]
    close: Callable[[], None]


class ObjectStore(Protocol):
    async def put_file(self, key: str, path: Path, content_type: str) -> None: ...

    async def get_bytes(self, key: str) -> bytes: ...

    async def open_read(self, key: str) -> ObjectReader: ...

    async def exists(self, key: str) -> bool: ...

    async def delete(self, key: str) -> None: ...

    async def check(self) -> None: ...

    def local_copy(self, key: str) -> AsyncIterator[Path]: ...


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        if not Path(key).is_absolute():
            validate_key(key)
        resolved = resolve_stored(self.root, key)
        try:
            resolved.relative_to(self.root.resolve())
        except ValueError as exc:
            raise ObjectMissingError(key) from exc
        return resolved

    async def put_file(self, key: str, path: Path, content_type: str) -> None:
        del content_type
        destination = self._resolve(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")

        def write() -> None:
            shutil.copyfile(path, temporary)
            os.replace(temporary, destination)

        try:
            await asyncio.to_thread(write)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    async def get_bytes(self, key: str) -> bytes:
        path = self._resolve(key)
        if not path.is_file():
            raise ObjectMissingError(key)
        return await asyncio.to_thread(path.read_bytes)

    async def open_read(self, key: str) -> ObjectReader:
        path = self._resolve(key)
        if not path.is_file():
            raise ObjectMissingError(key)
        handle = path.open("rb")
        size = path.stat().st_size

        def chunks() -> Iterator[bytes]:
            while True:
                block = handle.read(_CHUNK)
                if not block:
                    break
                yield block

        def close() -> None:
            handle.close()

        return ObjectReader(size=size, chunks=chunks(), close=close)

    async def exists(self, key: str) -> bool:
        path = self._resolve(key)
        return path.is_file()

    async def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            await asyncio.to_thread(path.unlink)

    async def check(self) -> None:
        if not self.root.is_dir():
            raise StorageUnavailableError()

    @asynccontextmanager
    async def local_copy(self, key: str) -> AsyncIterator[Path]:
        suffix = Path(key).suffix
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        handle.close()
        destination = Path(handle.name)
        try:
            data = await self.get_bytes(key)
            await asyncio.to_thread(destination.write_bytes, data)
            yield destination
        finally:
            destination.unlink(missing_ok=True)


class S3ObjectStore:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None

    def _s3(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            kwargs: dict[str, str] = {}
            if self._settings.s3_endpoint_url:
                kwargs["endpoint_url"] = self._settings.s3_endpoint_url
            if self._settings.s3_region:
                kwargs["region_name"] = self._settings.s3_region
            if self._settings.s3_access_key_id:
                kwargs["aws_access_key_id"] = self._settings.s3_access_key_id
                kwargs["aws_secret_access_key"] = self._settings.s3_secret_access_key
            config_kwargs: dict[str, object] = {
                "connect_timeout": 5,
                "read_timeout": 30,
                "retries": {"max_attempts": 3, "mode": "standard"},
                "request_checksum_calculation": "when_required",
                "response_checksum_validation": "when_required",
            }
            if self._settings.s3_force_path_style:
                config_kwargs["s3"] = {"addressing_style": "path"}
            self._client = boto3.client("s3", config=Config(**config_kwargs), **kwargs)
        return self._client

    def _fail(self, key: str, exc: Exception) -> None:
        from botocore.exceptions import BotoCoreError, ClientError

        code = type(exc).__name__
        if isinstance(exc, ClientError):
            error = exc.response.get("Error", {})
            code = str(error.get("Code") or code)
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            logger.error("storage key=%s code=%s", key, code)
            if code in {"NoSuchKey", "404", "NotFound"} or status == 404:
                raise ObjectMissingError(key) from exc
            raise StorageUnavailableError() from exc
        if isinstance(exc, (BotoCoreError, ConnectionError, TimeoutError, OSError)):
            logger.error("storage key=%s code=%s", key, code)
            raise StorageUnavailableError() from exc
        raise exc

    def _put_args(self, content_type: str) -> dict[str, str]:
        extra = {"ContentType": content_type}
        if self._settings.s3_server_side_encryption:
            extra["ServerSideEncryption"] = self._settings.s3_server_side_encryption
        if self._settings.s3_kms_key_id:
            extra["SSEKMSKeyId"] = self._settings.s3_kms_key_id
        return extra

    async def put_file(self, key: str, path: Path, content_type: str) -> None:
        validate_key(key)
        extra = self._put_args(content_type)

        def send() -> None:
            try:
                with path.open("rb") as handle:
                    self._s3().put_object(
                        Bucket=self._settings.s3_bucket,
                        Key=key,
                        Body=handle,
                        **extra,
                    )
            except Exception as exc:
                self._fail(key, exc)

        await asyncio.to_thread(send)

    async def get_bytes(self, key: str) -> bytes:
        validate_key(key)

        def read() -> bytes:
            try:
                response = self._s3().get_object(Bucket=self._settings.s3_bucket, Key=key)
                body = response["Body"]
                try:
                    return body.read()
                finally:
                    body.close()
            except Exception as exc:
                self._fail(key, exc)
                raise

        return await asyncio.to_thread(read)

    async def open_read(self, key: str) -> ObjectReader:
        validate_key(key)

        def open_body() -> ObjectReader:
            try:
                response = self._s3().get_object(Bucket=self._settings.s3_bucket, Key=key)
            except Exception as exc:
                self._fail(key, exc)
                raise
            body = response["Body"]
            size = int(response.get("ContentLength") or 0)

            def chunks() -> Iterator[bytes]:
                while True:
                    block = body.read(_CHUNK)
                    if not block:
                        break
                    yield block

            def close() -> None:
                body.close()

            return ObjectReader(size=size, chunks=chunks(), close=close)

        return await asyncio.to_thread(open_body)

    async def exists(self, key: str) -> bool:
        validate_key(key)

        def head() -> bool:
            try:
                self._s3().head_object(Bucket=self._settings.s3_bucket, Key=key)
                return True
            except Exception as exc:
                try:
                    self._fail(key, exc)
                except ObjectMissingError:
                    return False
                raise

        return await asyncio.to_thread(head)

    async def delete(self, key: str) -> None:
        validate_key(key)

        def remove() -> None:
            try:
                self._s3().delete_object(Bucket=self._settings.s3_bucket, Key=key)
            except Exception as exc:
                try:
                    self._fail(key, exc)
                except ObjectMissingError:
                    return
                raise

        await asyncio.to_thread(remove)

    async def check(self) -> None:
        def probe() -> None:
            try:
                self._s3().head_bucket(Bucket=self._settings.s3_bucket)
            except Exception as exc:
                self._fail(self._settings.s3_bucket, exc)

        await asyncio.to_thread(probe)

    @asynccontextmanager
    async def local_copy(self, key: str) -> AsyncIterator[Path]:
        suffix = Path(key).suffix
        handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        handle.close()
        destination = Path(handle.name)
        try:
            data = await self.get_bytes(key)
            await asyncio.to_thread(destination.write_bytes, data)
            yield destination
        finally:
            destination.unlink(missing_ok=True)


def build_object_store(settings: Settings) -> ObjectStore:
    if settings.storage_backend == "s3":
        from app.services.storage.s3_storage import S3Storage

        return S3Storage(settings)
    from app.services.storage.local_storage import LocalStorage

    return LocalStorage(settings.resolved_storage_dir)
