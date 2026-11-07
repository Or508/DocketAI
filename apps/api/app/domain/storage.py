from collections.abc import AsyncIterator
from typing import BinaryIO, Protocol


class StorageService(Protocol):
    async def upload_file(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str | None = None,
    ) -> None: ...

    async def download_file(self, key: str) -> bytes: ...

    def stream_file(self, key: str) -> AsyncIterator[bytes]: ...

    async def delete_file(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    async def get_sha256(self, key: str) -> str: ...
