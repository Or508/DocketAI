import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

pytest.importorskip("fitz")
pytest.importorskip("reportlab")
pytest.importorskip("pypdf")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

import pymupdf
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.db.session import session_scope
from app.domain.enums import CaseStatus
from app.domain.signing_links import hash_token
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.signing_link import SigningLink

_PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
).decode()
_ANSWERS = ["Dana Cohen", "123456782", "dana@example.com", "0501234567", "הרצל 1 תל אביב", "04/11/2026"]
_CASE_NAME = "Internal packet name"


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
    path.parent.mkdir(parents=True, exist_ok=True)
    form = canvas.Canvas(str(path))
    form.drawString(72, 720, text)
    form.save()


def _case(client: TestClient, name: str = _CASE_NAME) -> str:
    created = client.post("/cases", json={"name": name, "process_key": "onboarding", "client_name": "Dana"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _upload(client: TestClient, case_id: str, tmp_path: Path) -> dict:
    names = {"a-id.pdf": "identity card", "b-tax.pdf": "tax form 101", "c-bank.pdf": "bank confirmation"}
    files = []
    for name, text in names.items():
        path = tmp_path / name
        _write_pdf(path, text)
        files.append(("files", (name, path.read_bytes(), "application/pdf")))
    uploaded = client.post(f"/cases/{case_id}/upload", files=files)
    assert uploaded.status_code == 200, uploaded.text
    workspace = client.get(f"/cases/{case_id}").json()
    return {item["filename"]: item["document_id"] for item in workspace["gap"]["unrecognized"]}


def _classify(client: TestClient, case_id: str, unrecognized: dict[str, str]) -> None:
    mapping = {"a-id.pdf": "id_copy", "b-tax.pdf": "tax_form", "c-bank.pdf": "bank_confirmation"}
    for filename, document_type in mapping.items():
        classified = client.post(
            f"/cases/{case_id}/classify-manual",
            json={"document_id": unrecognized[filename], "document_type": document_type},
        )
        assert classified.status_code == 200, classified.text


def _fill(client: TestClient, case_id: str) -> None:
    for answer in _ANSWERS:
        current = client.post(f"/cases/{case_id}/chat", json={"message": answer})
        assert current.status_code == 200, current.text


def _ready(client: TestClient, tmp_path: Path) -> tuple[str, list[str]]:
    case_id = _case(client)
    unrecognized = _upload(client, case_id, tmp_path)
    document_ids = list(unrecognized.values())
    _classify(client, case_id, unrecognized)
    _fill(client, case_id)
    return case_id, document_ids


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def _hidden(blob: str, case_id: str, document_ids: list[str]) -> None:
    banned = [case_id, case_id.replace("-", ""), _CASE_NAME, *_document_forms(document_ids)]
    for secret in banned:
        assert secret not in blob


def _document_forms(document_ids: list[str]) -> list[str]:
    forms: list[str] = []
    for document_id in document_ids:
        forms.append(document_id)
        forms.append(document_id.replace("-", ""))
    return forms


async def _rows() -> tuple[list[tuple[str, object, str | None]], list[object]]:
    async with session_scope() as session:
        links = list(await session.scalars(select(SigningLink)))
        audits = list(await session.scalars(select(AuditLog)))
        return (
            [(link.token_hash, link.revoked_at, link.revoke_reason) for link in links],
            [audit.new_value for audit in audits],
        )


def test_only_the_hash_is_stored_and_a_second_link_replaces_the_first(
    client: TestClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")
    case_id, _ = _ready(client, tmp_path)
    first = client.post(f"/cases/{case_id}/signing-links")
    assert first.status_code == 201, first.text
    token = _token(first.json()["url"])
    assert token not in first.text.replace(first.json()["url"], "")

    links, audits = client.portal.call(_rows)
    assert links[0][0] == hash_token(token)
    stored = json.dumps(audits, default=str)
    assert token not in stored
    assert token not in "".join(item[0] for item in links)
    assert token not in caplog.text

    second = client.post(f"/cases/{case_id}/signing-links")
    assert second.status_code == 201, second.text
    links, _ = client.portal.call(_rows)
    replaced = next(item for item in links if item[0] == hash_token(token))
    assert replaced[1] is not None
    assert replaced[2] == "replaced"
    assert client.get("/portal", headers=_auth(token)).status_code == 410
    assert client.get("/portal", headers=_auth(_token(second.json()["url"]))).status_code == 200


def test_create_is_refused_until_the_documents_are_ready(client: TestClient, tmp_path: Path) -> None:
    draft = _case(client)
    assert client.post(f"/cases/{draft}/signing-links").status_code == 409

    missing = _case(client)
    _upload(client, missing, tmp_path)
    assert client.post(f"/cases/{missing}/signing-links").status_code == 409

    partial = _case(client)
    found = _upload(client, partial, tmp_path)
    one = client.post(
        f"/cases/{partial}/classify-manual",
        json={"document_id": found["a-id.pdf"], "document_type": "id_copy"},
    )
    assert one.status_code == 200, one.text
    assert client.post(f"/cases/{partial}/signing-links").status_code == 409

    case_id, _ = _ready(client, tmp_path)

    async def mark(status: CaseStatus) -> None:
        async with session_scope() as session:
            case = await session.get(Case, UUID(case_id))
            assert case is not None
            case.status = status
            await session.commit()

    async def mark_processing() -> None:
        await mark(CaseStatus.PROCESSING)

    async def mark_failed() -> None:
        await mark(CaseStatus.FAILED)

    async def mark_filling() -> None:
        await mark(CaseStatus.FILLING)

    client.portal.call(mark_processing)
    assert client.post(f"/cases/{case_id}/signing-links").status_code == 409
    client.portal.call(mark_failed)
    assert client.post(f"/cases/{case_id}/signing-links").status_code == 409
    client.portal.call(mark_filling)
    signed = client.post(
        f"/cases/{case_id}/fill-and-sign",
        json={"signature_png_base64": _PNG, "field_values": {}, "consent": True},
    )
    assert signed.status_code == 200, signed.text
    assert client.post(f"/cases/{case_id}/signing-links").status_code == 409


def test_expired_revoked_and_unknown_tokens_are_rejected(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    created = client.post(f"/cases/{case_id}/signing-links")
    token = _token(created.json()["url"])

    async def expire() -> None:
        async with session_scope() as session:
            link = await session.scalar(select(SigningLink).where(SigningLink.token_hash == hash_token(token)))
            assert link is not None
            link.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()

    client.portal.call(expire)
    assert client.get("/portal", headers=_auth(token)).status_code == 410

    fresh = client.post(f"/cases/{case_id}/signing-links")
    live = _token(fresh.json()["url"])
    assert client.delete(f"/cases/{case_id}/signing-link").status_code == 204
    assert client.get("/portal", headers=_auth(live)).status_code == 410
    assert client.get("/portal", headers=_auth("missing-token")).status_code == 404
    assert client.get("/portal").status_code == 404


def test_signer_payloads_hide_the_office_case(client: TestClient, tmp_path: Path) -> None:
    case_id, document_ids = _ready(client, tmp_path)
    note = client.post(f"/cases/{case_id}/chat", json={"message": "OFFICE-ONLY-NOTE"})
    assert note.status_code == 200, note.text
    created = client.post(f"/cases/{case_id}/signing-links")
    token = _token(created.json()["url"])
    view = client.get("/portal", headers=_auth(token))
    assert view.status_code == 200, view.text
    _hidden(view.text, case_id, document_ids)
    assert "OFFICE-ONLY-NOTE" not in view.text
    assert view.json()["client_name"] == "Dana"
    assert "gap" not in view.json()

    streamed = client.post("/portal/chat/stream", headers=_auth(token), json={"message": "hello"})
    assert streamed.status_code == 200, streamed.text
    assert "event: workspace" in streamed.text
    assert "could not finish" not in streamed.text
    _hidden(streamed.text, case_id, document_ids)
    assert "signing_blockers" not in streamed.text
    assert "OFFICE-ONLY-NOTE" not in streamed.text

    missing = client.get("/portal", headers=_auth("not-a-link"))
    _hidden(missing.text, case_id, document_ids)
    gone = client.delete(f"/cases/{case_id}/signing-link")
    assert gone.status_code == 204
    denied = client.get("/portal", headers=_auth(token))
    assert denied.status_code == 410
    _hidden(denied.text, case_id, document_ids)


def test_a_stale_digest_or_failed_fill_leaves_the_link_open(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    created = client.post(f"/cases/{case_id}/signing-links")
    token = _token(created.json()["url"])
    view = client.get("/portal", headers=_auth(token)).json()
    changed = client.post(f"/cases/{case_id}/fields", json={"key": "full_name", "value": "Noa Levi"})
    assert changed.status_code == 200, changed.text
    stale = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG, "review_digest": view["review_digest"], "consent": True},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"] == "The form changed. Please review it again."
    opened = client.get("/portal", headers=_auth(token))
    assert opened.status_code == 200
    assert opened.json()["state"] == "open"

    def boom(**_kwargs):
        raise RuntimeError("disk full")

    client.app.state.container.pdf_filler.fill_and_sign = boom
    digest = opened.json()["review_digest"]
    with pytest.raises(RuntimeError):
        client.post(
            "/portal/sign",
            headers=_auth(token),
            json={"signature_png_base64": _PNG, "review_digest": digest, "consent": True},
        )
    still = client.get("/portal", headers=_auth(token))
    assert still.status_code == 200
    assert still.json()["state"] == "open"
    office = client.get(f"/cases/{case_id}").json()
    assert office["case"]["status"] != "signed"


def test_signing_is_single_use_and_the_download_expires(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    created = client.post(f"/cases/{case_id}/signing-links")
    token = _token(created.json()["url"])
    view = client.get("/portal", headers=_auth(token)).json()
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG, "review_digest": view["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["state"] == "completed"
    office = client.get(f"/cases/{case_id}").json()
    file_hash = office["case"]["audit"]["file_sha256"]
    again = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG, "review_digest": view["review_digest"], "consent": True},
    )
    assert again.status_code == 409
    assert client.get(f"/cases/{case_id}").json()["case"]["audit"]["file_sha256"] == file_hash

    for path, body in (
        ("/portal/fields", {"key": "full_name", "value": "Dana Cohen"}),
        ("/portal/chat/stream", {"message": "hello"}),
        ("/portal/sign", {"signature_png_base64": _PNG, "review_digest": view["review_digest"], "consent": True}),
    ):
        refused = client.post(path, headers=_auth(token), json=body)
        assert refused.status_code == 409, refused.text
    assert client.get("/portal/preview", headers=_auth(token)).status_code == 409
    current = client.get("/portal", headers=_auth(token))
    assert current.status_code == 200
    assert current.json()["state"] == "completed"
    download = client.get("/portal/signed-document", headers=_auth(token))
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert "signed-document.pdf" in download.headers["content-disposition"]
    assert case_id not in download.headers["content-disposition"]

    async def end_download() -> None:
        async with session_scope() as session:
            link = await session.scalar(select(SigningLink).where(SigningLink.token_hash == hash_token(token)))
            assert link is not None
            link.download_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()

    client.portal.call(end_download)
    assert client.get("/portal/signed-document", headers=_auth(token)).status_code == 410

    changed_case, _ = _ready(client, tmp_path / "changed")
    made = client.post(f"/cases/{changed_case}/signing-links")
    changed_token = _token(made.json()["url"])
    digest = client.get("/portal", headers=_auth(changed_token)).json()["review_digest"]
    done = client.post(
        "/portal/sign",
        headers=_auth(changed_token),
        json={"signature_png_base64": _PNG, "review_digest": digest, "consent": True},
    )
    assert done.status_code == 200, done.text
    edited = client.post(f"/cases/{changed_case}/fields", json={"key": "full_name", "value": "Noa Levi"})
    assert edited.status_code == 200, edited.text
    assert client.get("/portal/signed-document", headers=_auth(changed_token)).status_code == 410


def test_office_signing_closes_an_open_link(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    created = client.post(f"/cases/{case_id}/signing-links")
    token = _token(created.json()["url"])
    signed = client.post(
        f"/cases/{case_id}/fill-and-sign",
        json={"signature_png_base64": _PNG, "field_values": {}, "consent": True},
    )
    assert signed.status_code == 200, signed.text
    assert client.get("/portal", headers=_auth(token)).status_code == 410

    async def reason() -> str | None:
        async with session_scope() as session:
            link = await session.scalar(select(SigningLink).where(SigningLink.token_hash == hash_token(token)))
            assert link is not None
            return link.revoke_reason

    assert client.portal.call(reason) == "signed_by_office"


def test_chat_cap_preview_and_closed_portal_routes(client: TestClient, tmp_path: Path) -> None:
    case_id, document_ids = _ready(client, tmp_path)
    created = client.post(f"/cases/{case_id}/signing-links")
    token = _token(created.json()["url"])
    client.app.state.container.settings.signing_link_max_chat_turns = 1
    first = client.post("/portal/chat/stream", headers=_auth(token), json={"message": "hello"})
    assert first.status_code == 200, first.text
    second = client.post("/portal/chat/stream", headers=_auth(token), json={"message": "again"})
    assert second.status_code == 429

    storage = tmp_path / "storage"
    before = sorted(path.relative_to(storage).as_posix() for path in storage.rglob("*") if path.is_file())
    preview = client.get("/portal/preview", headers=_auth(token))
    assert preview.status_code == 200
    assert preview.headers["cache-control"] == "no-store"
    after = sorted(path.relative_to(storage).as_posix() for path in storage.rglob("*") if path.is_file())
    assert before == after
    opened = pymupdf.open(stream=preview.content)
    text = "\n".join(page.get_text() for page in opened)
    opened.close()
    assert "DRAFT - NOT SIGNED" in text
    assert "Dana Cohen" in text
    _hidden(preview.content.decode("latin1", errors="ignore"), case_id, document_ids)

    for method, path in (
        ("POST", "/portal/upload"),
        ("POST", "/portal/classify"),
        ("POST", "/portal/classify-manual"),
        ("GET", f"/portal/documents/{document_ids[0]}/file"),
    ):
        response = client.request(method, path, headers=_auth(token))
        assert response.status_code == 404, response.text
