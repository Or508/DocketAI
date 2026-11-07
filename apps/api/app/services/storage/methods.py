import hashlib
import shutil
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import BinaryIO


class StorageMethods:
    """Shared StorageService operations. Subclasses provide the object-store primitives."""

    async def upload_file(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str | None = None,
    ) -> None:
        media = content_type or "application/octet-stream"
        with tempfile.NamedTemporaryFile(delete=False) as handle:
            if isinstance(data, (bytes, bytearray)):
                handle.write(bytes(data))
            else:
                shutil.copyfileobj(data, handle)
            path = Path(handle.name)
        try:
            await self.put_file(key, path, media)
        finally:
            path.unlink(missing_ok=True)

    async def download_file(self, key: str) -> bytes:
        return await self.get_bytes(key)

    async def stream_file(self, key: str) -> AsyncIterator[bytes]:
        reader = await self.open_read(key)
        try:
            for chunk in reader.chunks:
                yield chunk
        finally:
            reader.close()

    async def delete_file(self, key: str) -> None:
        await self.delete(key)

    async def get_sha256(self, key: str) -> str:
        return hashlib.sha256(await self.download_file(key)).hexdigest()
