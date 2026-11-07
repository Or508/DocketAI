import base64
import hashlib
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("reportlab")
pytest.importorskip("pypdf")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

import pymupdf
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAADIAAAAUCAIAAABAqPnNAAAALklEQVR4nO3OMQEAAAyDMPyb3jTw9SAKAnB7Fk9Xy6ll1DJqGbWMWkYto5ZRy3gIz6nxyF1oDwAAAABJRU5ErkJggg=="
)


def _write_pdf(path: Path, text: str) -> None:
    form = canvas.Canvas(str(path))
    form.drawString(72, 720, text)
    form.save()


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("QUEUE_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
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


def test_case_flow_from_upload_to_signed_pdf(client: TestClient, tmp_path: Path) -> None:
    created = client.post(
        "/cases",
        json={"name": "Dana Cohen", "process_key": "onboarding", "client_name": "Dana"},
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    assert client.get("/health").json()["database"] == "ok"
    assert any(item["key"] == "onboarding" for item in client.get("/processes").json())

    bundle = tmp_path / "bundle"
    bundle.mkdir()
    names = {
        "a-id.pdf": "identity card",
        "b-tax.pdf": "tax form 101",
        "c-bank.pdf": "bank confirmation",
    }
    handles = []
    for name, text in names.items():
        path = bundle / name
        _write_pdf(path, text)
        handles.append(path.open("rb"))
    upload = client.post(
        f"/cases/{case_id}/upload",
        files=[("files", (path.name, handle, "application/pdf")) for path, handle in zip(bundle.iterdir(), handles, strict=True)],
    )
    for handle in handles:
        handle.close()
    assert upload.status_code == 200, upload.text

    workspace = client.get(f"/cases/{case_id}")
    assert workspace.status_code == 200, workspace.text
    body = workspace.json()
    assert body["gap"]["pipeline"]["stage"] == "awaiting_input"
    unrecognized = {item["filename"]: item["document_id"] for item in body["gap"]["unrecognized"]}
    assert set(unrecognized) == set(names)
    mapping = {
        "a-id.pdf": "id_copy",
        "b-tax.pdf": "tax_form",
        "c-bank.pdf": "bank_confirmation",
    }
    for filename, document_type in mapping.items():
        classified = client.post(
            f"/cases/{case_id}/classify-manual",
            json={"document_id": unrecognized[filename], "document_type": document_type},
        )
        assert classified.status_code == 200, classified.text

    answers = [
        "Dana Cohen",
        "123456782",
        "dana@example.com",
        "0501234567",
        "הרצל 1 תל אביב",
        "04/11/2026",
    ]
    current = None
    for answer in answers:
        current = client.post(f"/cases/{case_id}/chat", json={"message": answer})
        assert current.status_code == 200, current.text
    assert current is not None
    filled = current.json()
    streamed = client.post(f"/cases/{case_id}/chat/stream", json={"message": "Nothing new to add"})
    assert streamed.status_code == 200, streamed.text
    assert "event: delta" in streamed.text
    assert "event: workspace" in streamed.text
    assert filled["ready_to_sign"] is True
    assert filled["field_values"]["national_id"] == "123456782"
    assert filled["field_values"]["start_date"] == "2026-11-04"
    assert filled["field_values"]["address_he"] == "הרצל 1 תל אביב"

    signed = client.post(
        f"/cases/{case_id}/fill-and-sign",
        json={"signature_png_base64": base64.b64encode(_PNG).decode(), "field_values": {}, "consent": True},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["case"]["download_ready"] is True

    download = client.get(f"/cases/{case_id}/signed-document")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")
    opened = pymupdf.open(stream=download.content)
    signed_text = "\n".join(page.get_text() for page in opened)
    opened.close()
    assert "Dana Cohen" in signed_text
    audit = signed.json()["case"]["audit"]
    assert audit["is_signed"] is True
    assert audit["signer_verification_id"].startswith("DV-")
    assert audit["content_sha256"] != audit["file_sha256"]
    assert audit["file_sha256"] == hashlib.sha256(download.content).hexdigest()
    assert audit["content_sha256"] in signed_text
    assert "Content SHA-256" in signed_text
    assert case_id not in signed_text
    assert audit["certificate"]["case_reference"] in signed_text
    assert "UTC" in signed_text and "Israel" in signed_text
    preview = next(iter(unrecognized.values()))
    source = client.get(f"/cases/{case_id}/documents/{preview}/file")
    assert source.status_code == 200
    assert source.content.startswith(b"%PDF")
    status = client.get(f"/cases/{case_id}/status")
    assert status.status_code == 200
    assert status.json()["missing"] == []
    assert status.json()["pipeline"]["stage"] == "signed"

    extra = tmp_path / "extra.pdf"
    _write_pdf(extra, "another page of the bundle with enough words to be a document")
    with extra.open("rb") as handle:
        uploaded = client.post(
            f"/cases/{case_id}/upload",
            files=[("files", (extra.name, handle, "application/pdf"))],
        )
    assert uploaded.status_code == 200, uploaded.text
    after = client.get(f"/cases/{case_id}")
    assert after.status_code == 200
    assert after.json()["case"]["status"] != "signed"
    assert after.json()["case"]["audit"]["is_signed"] is False
    assert after.json()["case"]["audit"]["file_sha256"] is None
    assert client.get(f"/cases/{case_id}/signed-document").status_code == 404
    assert client.post("/cases", json={"name": "Missing", "process_key": "no-such-process"}).status_code == 404
