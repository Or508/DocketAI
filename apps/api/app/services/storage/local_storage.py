from pathlib import Path

from app.services.object_store import LocalObjectStore
from app.services.storage.methods import StorageMethods


class LocalStorage(StorageMethods, LocalObjectStore):
    """Filesystem storage used for offline runs and the default test suite."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
