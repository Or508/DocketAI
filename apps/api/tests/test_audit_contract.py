import base64
import hashlib
import re
from datetime import datetime
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

from app.schemas.case import CaseAudit, CaseCertificate, CaseRead
from app.schemas.chat import ChatRequest, FieldUpdateRequest
from app.schemas.events import CaseProgressEvent, StreamError
from app.schemas.gap import FormAnchorRef, OpenSlot, PipelineProgress, UnboundAnchor
from app.schemas.process import FieldSource
from app.schemas.workspace import CaseWorkspace
from app.schemas.portal import PortalProcess, PortalSeal, PortalSignRequest, PortalView, SigningLinkCreated, SigningLinkRead

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAADIAAAAUCAIAAABAqPnNAAAALklEQVR4nO3OMQEAAAyDMPyb3jTw9SAKAnB7Fk9Xy6ll1DJqGbWMWkYto5ZRy3gIz6nxyF1oDwAAAABJRU5ErkJggg=="
)
_PAIRS = {
    "CaseCertificate": CaseCertificate,
    "CaseAudit": CaseAudit,
    "CaseRead": CaseRead,
    "PipelineProgress": PipelineProgress,
    "CaseProgressEvent": CaseProgressEvent,
    "FieldUpdateRequest": FieldUpdateRequest,
    "ChatRequest": ChatRequest,
    "StreamError": StreamError,
    "SigningLinkRead": SigningLinkRead,
    "SigningLinkCreated": SigningLinkCreated,
    "PortalProcess": PortalProcess,
    "PortalSeal": PortalSeal,
    "PortalView": PortalView,
    "PortalSignRequest": PortalSignRequest,
    "FieldSource": FieldSource,
    "FormAnchorRef": FormAnchorRef,
    "OpenSlot": OpenSlot,
    "UnboundAnchor": UnboundAnchor,
    "CaseWorkspace": CaseWorkspace,
}


def _interface_fields(source: str, name: str) -> list[str]:
    match = re.search(rf"export interface {name} \{{(.*?)\n\}}", source, re.DOTALL)
    assert match is not None, name
    return re.findall(r"^\s*(\w+)\??:", match.group(1), re.MULTILINE)


def test_shared_types_match_api_models() -> None:
    source = (Path(__file__).resolve().parents[3] / "packages" / "shared-types" / "src" / "index.ts").read_text(
        encoding="utf-8"
    )
    for name, model in _PAIRS.items():
        assert _interface_fields(source, name) == list(model.model_fields)


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


def _write_pdf(path: Path, text: str) -> None:
    form = canvas.Canvas(str(path))
    form.drawString(72, 720, text)
    form.save()


def test_audit_record_follows_the_signed_file(client: TestClient, tmp_path: Path) -> None:
    created = client.post(
        "/cases",
        json={"name": "Dana Cohen", "process_key": "onboarding", "client_name": "Dana"},
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    before = created.json()["audit"]
    assert before["is_signed"] is False
    assert before["signed_at"] is None
    assert before["signer_verification_id"] is None
    assert before["content_sha256"] is None
    assert before["file_sha256"] is None

    names = {
        "a-id.pdf": "identity card",
        "b-tax.pdf": "tax form 101",
        "c-bank.pdf": "bank confirmation",
    }
    files = []
    for name, text in names.items():
        path = tmp_path / name
        _write_pdf(path, text)
        files.append(("files", (name, path.read_bytes(), "application/pdf")))
    uploaded = client.post(f"/cases/{case_id}/upload", files=files)
    assert uploaded.status_code == 200, uploaded.text
    workspace = client.get(f"/cases/{case_id}").json()
    unrecognized = {item["filename"]: item["document_id"] for item in workspace["gap"]["unrecognized"]}
    mapping = {"a-id.pdf": "id_copy", "b-tax.pdf": "tax_form", "c-bank.pdf": "bank_confirmation"}
    for filename, document_type in mapping.items():
        classified = client.post(
            f"/cases/{case_id}/classify-manual",
            json={"document_id": unrecognized[filename], "document_type": document_type},
        )
        assert classified.status_code == 200, classified.text
    for answer in ["Dana Cohen", "123456782", "dana@example.com", "0501234567", "הרצל 1 תל אביב", "04/11/2026"]:
        current = client.post(f"/cases/{case_id}/chat", json={"message": answer})
        assert current.status_code == 200, current.text

    signed = client.post(
        f"/cases/{case_id}/fill-and-sign",
        json={"signature_png_base64": base64.b64encode(_PNG).decode(), "field_values": {}, "consent": True},
    )
    assert signed.status_code == 200, signed.text
    audit = signed.json()["case"]["audit"]
    assert audit["is_signed"] is True
    download = client.get(f"/cases/{case_id}/signed-document")
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == audit["file_sha256"]
    opened = pymupdf.open(stream=download.content)
    text = "\n".join(page.get_text() for page in opened)
    opened.close()
    assert audit["content_sha256"] in text
    assert audit["content_sha256"] != audit["file_sha256"]
    parsed = datetime.fromisoformat(audit["signed_at"])
    assert parsed.tzinfo is not None

    changed = client.post(
        f"/cases/{case_id}/fields",
        json={"key": "full_name", "value": "Noa Levi"},
    )
    assert changed.status_code == 200, changed.text
    cleared = changed.json()["case"]["audit"]
    assert cleared["is_signed"] is False
    assert cleared["signed_at"] is None
    assert cleared["signer_verification_id"] is None
    assert cleared["content_sha256"] is None
    assert cleared["file_sha256"] is None
