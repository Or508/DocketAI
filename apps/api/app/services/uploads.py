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


_SUFFIX = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
}
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
# Formats the reader does not open are redrawn as PNG after the bounded check.
_REDRAWN = {"image/gif", "image/bmp"}


def detect_mime(header: bytes) -> str | None:
    """The file type from its first bytes. The name and extension are not trusted."""
    if header.startswith(b"%PDF"):
        return "application/pdf"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return "image/tiff"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"BM"):
        return "image/bmp"
    if header[4:8] == b"ftyp" and header[8:12] in _HEIF_BRANDS:
        return "image/heic"
    return None


def stored_suffix(mime: str) -> str:
    return _SUFFIX.get(mime, "")


def normalize_image(path: Path, mime: str) -> tuple[Path, str]:
    """Redraw a GIF or BMP as an RGB PNG. Every other accepted type is kept as uploaded."""
    if mime not in _REDRAWN:
        return path, mime
    from PIL import Image

    target = path.with_suffix(".normalized.png")
    with Image.open(path) as image:
        image.seek(0)
        image.convert("RGB").save(target, format="PNG")
    path.unlink(missing_ok=True)
    return target, "image/png"


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
                    header += chunk[: 16 - len(header)]  # enough for every signature in detect_mime
                hasher.update(chunk)
                handle.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    if size == 0:
        dest.unlink(missing_ok=True)
        raise BadRequestError(f"{filename} is empty.")

    mime = detect_mime(header)
    if mime is None:
        dest.unlink(missing_ok=True)
        raise BadRequestError(f"{filename} is not a PDF or a supported image.")
    if mime == "image/heic":
        dest.unlink(missing_ok=True)
        raise BadRequestError(f"{filename} is a HEIC photo. Save it as JPEG or PNG and upload it again.")

    return StoredUpload(
        original_filename=filename,
        storage_path=str(dest),
        mime_type=mime,
        file_size=size,
        content_hash=hasher.hexdigest(),
    )
