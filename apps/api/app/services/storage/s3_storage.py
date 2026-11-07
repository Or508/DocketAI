from app.core.config import Settings
from app.services.object_store import S3ObjectStore
from app.services.storage.methods import StorageMethods


class S3Storage(StorageMethods, S3ObjectStore):
    """S3-compatible storage. Set an endpoint for a service other than AWS."""

    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
