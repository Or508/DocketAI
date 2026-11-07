import asyncio
import json
import struct
import zlib
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

import fitz
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.core.exceptions import BadRequestError
from app.core.paths import REPO_ROOT
from app.models.document import Document
from app.services import preflight as preflight_module
from app.services.preflight import preflight


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "preflight_timeout_seconds": 20,
        "preflight_memory_mb": 768,
        "preflight_max_pages": 300,
        "preflight_max_page_inches": 200,
        "preflight_max_decompressed_mb": 512,
        "preflight_max_image_pixels": 50_000_000,
        "preflight_reject_pdf_javascript": True,
        "clamav_host": "",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _png(width: int, height: int, *, mark: bool = True) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            rows.extend(b"\x00\x00\x00" if mark and x == 0 and y == 0 else b"\xff\xff\xff")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows)))
        + chunk(b"IEND", b"")
    )


def _raw_pdf(action: str) -> bytes:
    body = (
        "%PDF-1.4\n"
        "1 0 obj\n"
        f"<< /Type /Catalog /Pages 2 0 R /OpenAction {action} >>\n"
        "endobj\n"
        "2 0 obj\n"
        "<< /Type /Pages /Count 1 /Kids [3 0 R] >>\n"
        "endobj\n"
        "3 0 obj\n"
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\n"
        "endobj\n"
        "trailer << /Root 1 0 R >>\n"
        "%%EOF\n"
    )
    return body.encode("ascii")


def test_sample_pdf_and_small_png_are_accepted(tmp_path: Path) -> None:
    sample = REPO_ROOT / "scripts" / "ci" / "fixtures" / "sample.pdf"
    settings = _settings()
    pages = asyncio.run(preflight(sample, "application/pdf", settings, "sample.pdf"))
    assert pages == 1
    image = tmp_path / "mark.png"
    image.write_bytes(_png(50, 20))
    frames = asyncio.run(preflight(image, "image/png", settings, "mark.png"))
    assert frames == 1


def test_encrypted_pdf_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "locked.pdf"

    def build(document: fitz.Document) -> None:
        document.new_page()

    document = fitz.open()
    build(document)
    document.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="user-secret", owner_pw="owner-secret")
    document.close()
    with pytest.raises(BadRequestError, match="password-protected") as caught:
        asyncio.run(preflight(path, "application/pdf", _settings(), "locked.pdf"))
    assert "user-secret" not in str(caught.value)


def test_too_many_pages_and_oversized_page_are_rejected(tmp_path: Path) -> None:
    many = tmp_path / "many.pdf"
    document = fitz.open()
    for _ in range(301):
        document.new_page()
    document.save(many)
    document.close()
    with pytest.raises(BadRequestError, match="too many pages"):
        asyncio.run(preflight(many, "application/pdf", _settings(), "many.pdf"))

    wide = tmp_path / "wide.pdf"
    document = fitz.open()
    document.new_page(width=300 * 72, height=72)
    document.save(wide)
    document.close()
    with pytest.raises(BadRequestError, match="too large"):
        asyncio.run(preflight(wide, "application/pdf", _settings(), "wide.pdf"))


def test_embedded_file_launch_and_javascript_are_rejected(tmp_path: Path) -> None:
    embedded = tmp_path / "embedded.pdf"
    document = fitz.open()
    document.new_page()
    document.embfile_add("note.txt", b"hello")
    document.save(embedded)
    document.close()
    with pytest.raises(BadRequestError, match="embedded files or actions"):
        asyncio.run(preflight(embedded, "application/pdf", _settings(), "embedded.pdf"))

    launch = tmp_path / "launch.pdf"
    launch.write_bytes(_raw_pdf("<< /S /Launch /F (calc) >>"))
    with pytest.raises(BadRequestError, match="embedded files or actions"):
        asyncio.run(preflight(launch, "application/pdf", _settings(), "launch.pdf"))

    script = tmp_path / "script.pdf"
    script.write_bytes(_raw_pdf("<< /S /JavaScript /JS (app.alert\\(1\\)) >>"))
    with pytest.raises(BadRequestError, match="embedded files or actions"):
        asyncio.run(preflight(script, "application/pdf", _settings(), "script.pdf"))
    pages = asyncio.run(
        preflight(script, "application/pdf", _settings(preflight_reject_pdf_javascript=False), "script.pdf")
    )
    assert pages == 1


def test_png_over_the_pixel_cap_is_rejected(tmp_path: Path) -> None:
    image = tmp_path / "wide.png"
    image.write_bytes(_png(50, 20))
    with pytest.raises(BadRequestError, match="too large"):
        asyncio.run(
            preflight(image, "image/png", _settings(preflight_max_image_pixels=10), "wide.png")
        )


def test_pixel_cap_ignores_the_dpi_tag(tmp_path: Path) -> None:
    from PIL import Image

    image = tmp_path / "dense.png"
    # 3000 x 2000 = 6 MP. At 600 DPI the page rect is only 360 x 240 points.
    Image.new("L", (3000, 2000), 255).save(image, dpi=(600, 600))
    with pytest.raises(BadRequestError, match="too large"):
        asyncio.run(
            preflight(image, "image/png", _settings(preflight_max_image_pixels=5_000_000), "dense.png")
        )


def test_hung_worker_is_killed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(preflight_module, "WORKER_MODULE", "tests.worker_hang")
    sample = tmp_path / "sample.pdf"
    sample.write_bytes((REPO_ROOT / "scripts" / "ci" / "fixtures" / "sample.pdf").read_bytes())
    with pytest.raises(BadRequestError, match="could not be checked safely"):
        asyncio.run(preflight(sample, "application/pdf", _settings(preflight_timeout_seconds=1), "sample.pdf"))


def test_crashed_worker_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(preflight_module, "WORKER_MODULE", "tests.worker_crash")
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"%PDF-1.4\n")
    with pytest.raises(BadRequestError, match="could not be checked safely"):
        asyncio.run(preflight(sample, "application/pdf", _settings(), "sample.pdf"))


def test_worker_environment_omits_secrets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-value")
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "s3-test-value")
    monkeypatch.setattr(preflight_module, "WORKER_MODULE", "tests.worker_env")
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"%PDF-1.4\n")
    line = asyncio.run(preflight_module._run_worker(sample, "application/pdf", _settings()))
    payload = json.loads(line)
    assert "GEMINI_API_KEY" not in payload["keys"]
    assert "S3_SECRET_ACCESS_KEY" not in payload["keys"]
    assert "gemini-test-value" not in line
    assert "s3-test-value" not in line


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("QUEUE_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("CLAMAV_HOST", "")
    from app.core.config import get_settings
    from app.db.session import reset_db

    get_settings.cache_clear()
    reset_db()
    from app.main import app

    with TestClient(app) as test_client:
        from tests.support import authenticate

        authenticate(test_client)
        yield test_client
    reset_db()
    get_settings.cache_clear()


def test_rejected_upload_stores_nothing(client: TestClient, tmp_path: Path) -> None:
    created = client.post("/cases", json={"name": "CI sample", "process_key": "onboarding"})
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    locked = tmp_path / "locked.pdf"
    document = fitz.open()
    document.new_page()
    document.save(locked, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="user-secret", owner_pw="owner-secret")
    document.close()
    uploaded = client.post(
        f"/cases/{case_id}/upload",
        files={"files": ("locked.pdf", locked.read_bytes(), "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    body = uploaded.json()
    assert body["accepted_filenames"] == []
    assert body["rejected"] == [
        {"filename": "locked.pdf", "reason": "locked.pdf is password-protected."}
    ]
    assert body["workspace"]["case"]["document_count"] == 0
    assert "user-secret" not in uploaded.text
    assert not any(path.is_file() for path in (tmp_path / "storage").rglob("*"))

    async def rows() -> int:
        from app.db.session import session_scope

        async with session_scope() as session:
            return len((await session.scalars(select(Document))).all())

    assert client.portal.call(rows) == 0
