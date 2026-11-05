import hashlib
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.exceptions import BadRequestError

_ALLOWED = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
}


def sniff_mime(header: bytes, suffix: str) -> str | None:
    expected = _ALLOWED.get(suffix)
    if expected is None:
        return None
    if suffix == ".pdf" and header.startswith(b"%PDF"):
        return expected
    if suffix == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"):
        return expected
    if suffix in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"):
        return expected
    if suffix in {".tif", ".tiff"} and (header.startswith(b"II*\x00") or header.startswith(b"MM\x00*")):
        return expected
    if suffix == ".webp" and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return expected
    return None


@dataclass(frozen=True)
class StoredUpload:
    original_filename: str
    storage_path: str
    mime_type: str
    file_size: int
    content_hash: str


def _display_name(raw: str | None) -> str:
    name = Path(raw or "upload").name.strip() or "upload"
    return name[:180]


async def store_upload(upload: UploadFile, dest: Path, *, max_bytes: int) -> StoredUpload:
    filename = _display_name(upload.filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED:
        raise BadRequestError(f"{filename} is not a PDF or a supported image.")

    dest.parent.mkdir(parents=True, exist_ok=True)
    hasher = hashlib.sha256()
    size = 0
    header = b""
    try:
        with dest.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > max_bytes:
                    raise BadRequestError(f"{filename} exceeds the {max_bytes // (1024 * 1024)} MB limit.")
                if len(header) < 16:
                    header += chunk[: 16 - len(header)]
                hasher.update(chunk)
                handle.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    if size == 0:
        dest.unlink(missing_ok=True)
        raise BadRequestError(f"{filename} is empty.")

    mime = sniff_mime(header, suffix)
    if mime is None:
        dest.unlink(missing_ok=True)
        raise BadRequestError(f"{filename} does not match its extension.")

    return StoredUpload(
        original_filename=filename,
        storage_path=str(dest),
        mime_type=mime,
        file_size=size,
        content_hash=hasher.hexdigest(),
    )
