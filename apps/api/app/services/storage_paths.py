from pathlib import Path


def storage_relative(root: Path, path: Path) -> str:
    """Store uploads relative to the shared storage root so another container can open them."""
    return path.resolve().relative_to(root.resolve()).as_posix()


def resolve_stored(root: Path, stored: str) -> Path:
    path = Path(stored)
    if path.is_absolute():
        return path.resolve()
    return (root.resolve() / path).resolve()
