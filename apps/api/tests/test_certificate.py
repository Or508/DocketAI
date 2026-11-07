import base64
import hashlib
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("fitz")
pytest.importorskip("reportlab")
pytest.importorskip("pypdf")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

import pymupdf
from fastapi.testclient import TestClient
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from app.db.session import session_scope
from app.domain.certificate import format_times
from app.models.case import Case
from app.services.storage_paths import resolve_stored

_PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAADIAAAAUCAIAAABAqPnNAAAALklEQVR4nO3OMQEAAAyDMPyb3jTw9SAKAnB7Fk9Xy6ll1DJqGbWMWkYto5ZRy3gIz6nxyF1oDwAAAABJRU5ErkJggg=="
    )
).decode()
_ANSWERS = ["Dana Cohen", "123456782", "dana@example.com", "0501234567", "הרצל 1 תל אביב", "04/11/2026"]


@pytest.fixture()
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
    path.parent.mkdir(parents=True, exist_ok=True)
    form = canvas.Canvas(str(path))
    form.drawString(72, 720, text)
    form.save()


def _ready(client: TestClient, tmp_path: Path, *, name: str, client_name: str) -> str:
    created = client.post("/cases", json={"name": name, "process_key": "onboarding", "client_name": client_name})
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    names = {"a-id.pdf": "identity card", "b-tax.pdf": "tax form 101", "c-bank.pdf": "bank confirmation"}
    files = []
    for filename, text in names.items():
        path = tmp_path / filename
        _write_pdf(path, text)
        files.append(("files", (filename, path.read_bytes(), "application/pdf")))
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
    for answer in _ANSWERS:
        current = client.post(f"/cases/{case_id}/chat", json={"message": answer})
        assert current.status_code == 200, current.text
    return case_id


def _pdf_text(data: bytes) -> str:
    document = pymupdf.open(stream=data)
    try:
        return "\n".join(page.get_text() for page in document)
    finally:
        document.close()


def _sign_office(client: TestClient, case_id: str, **headers: str):
    return client.post(
        f"/cases/{case_id}/fill-and-sign",
        json={"signature_png_base64": _PNG, "field_values": {}, "consent": True},
        headers=headers,
    )


async def _column(case_id: str):
    async with session_scope() as session:
        case = await session.get(Case, UUID(case_id))
        assert case is not None
        return case


def test_zone_abbreviations() -> None:
    july = format_times(datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc))
    january = format_times(datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc))
    assert july[1].endswith("IDT")
    assert january[1].endswith("IST")


@pytest.mark.local_storage
def test_signed_packet_carries_a_certificate(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="HIDDEN-CASE-LABEL", client_name="נועה לוי")
    transport = client._transport
    original = transport.client
    transport.client = ("198.51.100.20", 1234)
    try:
        signed = _sign_office(client, case_id, **{"user-agent": "OfficeDesk/9"})
    finally:
        transport.client = original
    assert signed.status_code == 200, signed.text
    audit = signed.json()["case"]["audit"]
    certificate = audit["certificate"]
    assert certificate["channel"] == "office"
    assert certificate["signer_ip"] == "198.51.100.20"
    assert certificate["signer_user_agent"] == "OfficeDesk/9"
    assert certificate["case_reference"].startswith("DK-")
    assert len(certificate["case_reference"]) == 15

    download = client.get(f"/cases/{case_id}/signed-document")
    assert download.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == audit["file_sha256"]
    document = pymupdf.open(stream=download.content)
    template = pymupdf.open(tmp_path / "templates" / "onboarding-v1.pdf")
    try:
        assert document.page_count == template.page_count + 1
        assert certificate["total_pages"] == document.page_count
        text = "\n".join(page.get_text() for page in document)
        last = document[-1].get_text()
        assert "Certificate of Completion" in last
        assert certificate["case_reference"] in last
        assert audit["content_sha256"] in last
        assert audit["signer_verification_id"] in last
        assert "Case created" in last
        assert "Data collection completed" in last
        assert "Signed" in last
        assert "Signing link issued" not in last
        for index, page in enumerate(document, start=1):
            assert f"Page {index} of {document.page_count}" in page.get_text()
            assert list(page.widgets() or []) == []
        assert document[-1].get_images()
        assert any("\u0590" <= character <= "\u05FF" for character in last)
    finally:
        document.close()
        template.close()
    assert PdfReader(BytesIO(download.content)).get_fields() in (None, {})
    assert case_id not in text
    assert case_id.replace("-", "") not in text
    assert "HIDDEN-CASE-LABEL" not in text
    utc, local = format_times(datetime.fromisoformat(audit["signed_at"]))
    assert utc in text
    assert local in text

    stored = client.portal.call(_column, case_id)
    form = resolve_stored(tmp_path / "storage", stored.content_path)
    assert hashlib.sha256(form.read_bytes()).hexdigest() == audit["content_sha256"]
    assert audit["content_sha256"] != audit["file_sha256"]

    one = client.get(f"/cases/{case_id}/certificate")
    assert one.status_code == 200
    assert one.headers["content-type"].startswith("application/pdf")
    assert 'filename="certificate.pdf"' in one.headers["content-disposition"]
    assert one.headers["cache-control"] == "no-store"
    opened = pymupdf.open(stream=one.content)
    try:
        assert opened.page_count == 1
        assert "Certificate of Completion" in opened[0].get_text()
    finally:
        opened.close()


def test_portal_records_forwarded_client_details(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="HIDDEN-CASE-LABEL", client_name="Dana")
    created = client.post(f"/cases/{case_id}/signing-links")
    token = created.json()["url"].rstrip("/").rsplit("/", 1)[-1]
    agent = "B" * 256
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Portal-Client-Ip": "not-an-address",
        "X-Portal-User-Agent": agent,
    }
    view = client.get("/portal", headers=headers)
    assert view.status_code == 200, view.text
    signed = client.post(
        "/portal/sign",
        headers=headers,
        json={"signature_png_base64": _PNG, "review_digest": view.json()["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    body = signed.text
    assert "not-an-address" not in body
    assert agent not in body
    assert "certificate_data" not in body
    assert "signer_ip" not in body
    refused = client.post("/portal/chat/stream", headers=headers, json={"message": "hello"})
    missing = client.post("/portal/fields", headers=headers, json={"key": "nope", "value": "x"})
    for payload in (body, refused.text, missing.text, view.text):
        assert "not-an-address" not in payload
        assert agent not in payload
        assert "certificate_data" not in payload
        assert "signer_user_agent" not in payload

    office = client.get(f"/cases/{case_id}").json()["case"]["audit"]
    assert office["certificate"]["signer_ip"] is None
    assert office["certificate"]["signer_user_agent"] == agent
    assert office["certificate"]["channel"] == "portal"
    assert office["certificate"]["link_issued_at"]
    download = client.get(f"/cases/{case_id}/signed-document")
    text = _pdf_text(download.content)
    compact = "".join(text.split())
    assert agent in compact
    assert "not-an-address" not in text
    assert "Not recorded" in text
    assert "Signing link issued" in text
    assert case_id not in text
    assert "HIDDEN-CASE-LABEL" not in text


def test_data_completion_follows_required_fields(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Completion", client_name="Dana")
    stored = client.portal.call(_column, case_id)
    assert stored.data_completed_at is not None

    async def drop_date() -> None:
        async with session_scope() as session:
            case = await session.get(Case, UUID(case_id))
            assert case is not None
            values = dict(case.field_values or {})
            values.pop("start_date", None)
            case.field_values = values
            await session.commit()

    client.portal.call(drop_date)
    changed = client.post(f"/cases/{case_id}/fields", json={"key": "email", "value": "dana@example.com"})
    assert changed.status_code == 200, changed.text
    cleared = client.portal.call(_column, case_id)
    assert cleared.data_completed_at is None


def test_older_packet_has_no_certificate(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Older", client_name="Dana")
    signed = _sign_office(client, case_id)
    assert signed.status_code == 200, signed.text

    async def forget() -> None:
        async with session_scope() as session:
            case = await session.get(Case, UUID(case_id))
            assert case is not None
            case.certificate_data = None
            await session.commit()

    client.portal.call(forget)
    audit = client.get(f"/cases/{case_id}").json()["case"]["audit"]
    assert audit["is_signed"] is True
    assert audit["certificate"] is None
    assert client.get(f"/cases/{case_id}/certificate").status_code == 404


@pytest.mark.local_storage
def test_field_change_clears_the_certificate_and_retains_the_file(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Mutable", client_name="Dana")
    signed = _sign_office(client, case_id)
    assert signed.status_code == 200, signed.text
    stored = client.portal.call(_column, case_id)
    form = resolve_stored(tmp_path / "storage", stored.content_path)
    assert form.is_file()
    changed = client.post(f"/cases/{case_id}/fields", json={"key": "full_name", "value": "Noa Levi"})
    assert changed.status_code == 200, changed.text
    assert form.is_file()
    cleared = client.portal.call(_column, case_id)
    assert cleared.certificate_data is None
    assert cleared.case_reference == stored.case_reference
    assert client.get(f"/cases/{case_id}/certificate").status_code == 404


def test_failed_fill_leaves_no_files_and_keeps_the_link(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Retry", client_name="Dana")
    created = client.post(f"/cases/{case_id}/signing-links")
    token = created.json()["url"].rstrip("/").rsplit("/", 1)[-1]
    view = client.get("/portal", headers={"Authorization": f"Bearer {token}"})
    written: list[Path] = []

    def boom(**kwargs):
        output = kwargs["output_path"]
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"signed")
        form = output.with_name(output.stem + "-form.pdf")
        form.write_bytes(b"form")
        written.extend([output, form])
        raise RuntimeError("fill failed")

    client.app.state.container.pdf_filler.fill_and_sign = boom
    with pytest.raises(RuntimeError):
        client.post(
            "/portal/sign",
            headers={"Authorization": f"Bearer {token}"},
            json={"signature_png_base64": _PNG, "review_digest": view.json()["review_digest"], "consent": True},
        )
    assert written
    assert all(not path.exists() for path in written)
    still = client.get("/portal", headers={"Authorization": f"Bearer {token}"})
    assert still.status_code == 200
    assert still.json()["state"] == "open"


def test_office_sign_requires_consent(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Consent", client_name="Dana")
    refused = client.post(
        f"/cases/{case_id}/fill-and-sign",
        json={"signature_png_base64": _PNG, "field_values": {}},
    )
    assert refused.status_code == 422
    assert client.get(f"/cases/{case_id}").json()["case"]["status"] != "signed"


def test_portal_sign_with_a_real_forwarded_address(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Forwarded", client_name="Dana")
    created = client.post(f"/cases/{case_id}/signing-links")
    token = created.json()["url"].rstrip("/").rsplit("/", 1)[-1]
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Portal-Client-Ip": "203.0.113.77",
        "X-Portal-User-Agent": "SignerProbe/1",
    }
    view = client.get("/portal", headers=headers)
    signed = client.post(
        "/portal/sign",
        headers=headers,
        json={"signature_png_base64": _PNG, "review_digest": view.json()["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    audit = client.get(f"/cases/{case_id}").json()["case"]["audit"]["certificate"]
    assert audit["signer_ip"] == "203.0.113.77"
    assert audit["signer_user_agent"] == "SignerProbe/1"
    text = _pdf_text(client.get(f"/cases/{case_id}/signed-document").content)
    assert "203.0.113.77" in text
    assert "SignerProbe/1" in text
    assert "203.0.113.77" not in signed.text
    assert "SignerProbe/1" not in signed.text


def test_office_cannot_replace_a_portal_signed_packet(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Portal first", client_name="Dana Cohen")
    made = client.post(f"/cases/{case_id}/signing-links")
    assert made.status_code == 201, made.text
    headers = {"Authorization": f"Bearer {made.json()['url'].rsplit('/', 1)[1]}"}
    view = client.get("/portal", headers=headers).json()
    signed = client.post(
        "/portal/sign",
        headers=headers,
        json={"signature_png_base64": _PNG, "review_digest": view["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    before = client.get(f"/cases/{case_id}").json()
    assert before["ready_to_sign"] is False
    packet = client.get("/portal/signed-document", headers=headers).content

    again = _sign_office(client, case_id)

    assert again.status_code == 409, again.text
    after = client.get(f"/cases/{case_id}").json()["case"]["audit"]
    assert after == before["case"]["audit"]
    assert after["certificate"]["channel"] == "portal"
    download = client.get("/portal/signed-document", headers=headers)
    assert download.status_code == 200
    assert download.content == packet


def test_signed_case_can_be_signed_again_only_after_invalidation(client: TestClient, tmp_path: Path) -> None:
    case_id = _ready(client, tmp_path, name="Office first", client_name="Dana Cohen")
    first = _sign_office(client, case_id)
    assert first.status_code == 200, first.text
    original = first.json()["case"]["audit"]["file_sha256"]

    repeat = _sign_office(client, case_id)
    assert repeat.status_code == 409, repeat.text
    assert client.get(f"/cases/{case_id}").json()["case"]["audit"]["file_sha256"] == original

    changed = client.post(f"/cases/{case_id}/fields", json={"key": "email", "value": "new@example.com"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["ready_to_sign"] is True
    resigned = _sign_office(client, case_id)
    assert resigned.status_code == 200, resigned.text
    assert resigned.json()["case"]["audit"]["file_sha256"] != original
