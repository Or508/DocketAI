import hashlib
import io
import json
import zipfile
from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("reportlab")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.domain.archive import audit_entry, source_name
from app.models.audit_log import AuditLog
from app.models.signing_link import SigningLink
from tests.support import authenticate
from tests.test_case_forms import _office_form
from tests.test_portal import _PNG, _auth, _ready, _token

_SIGN = {"signature_png_base64": _PNG, "field_values": {}, "consent": True}
_OFFICE_IP = "203.0.113.9"
_OFFICE_AGENT = "OfficeBrowser/9"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("QUEUE_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    from app.db.session import reset_db

    get_settings.cache_clear()
    reset_db()
    from app.main import app

    with TestClient(app) as test_client:
        authenticate(test_client)
        yield test_client
    reset_db()
    get_settings.cache_clear()


def _archive(client: TestClient, case_id: str) -> tuple[zipfile.ZipFile, dict, str]:
    response = client.get(f"/cases/{case_id}/archive")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == f'attachment; filename="case_{case_id}_archive.zip"'
    assert int(response.headers["content-length"]) == len(response.content)
    bundle = zipfile.ZipFile(io.BytesIO(response.content))
    assert bundle.testzip() is None
    raw = bundle.read("verification_manifest.json").decode("utf-8")
    return bundle, json.loads(raw), raw


def _audit_rows(client: TestClient, case_id: str) -> list[AuditLog]:
    async def rows() -> list[AuditLog]:
        async with session_scope() as session:
            found = await session.scalars(
                select(AuditLog).where(AuditLog.case_id == UUID(case_id)).order_by(AuditLog.created_at, AuditLog.id)
            )
            return list(found)

    return client.portal.call(rows)


def _actions(client: TestClient, case_id: str) -> list[str]:
    return [str(getattr(row.action, "value", row.action)) for row in _audit_rows(client, case_id)]


def _other_office(client: TestClient) -> dict[str, str]:
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    return {"Authorization": f"Bearer {other['token']}"}


# Archive


def test_signed_archive_holds_the_exact_signed_pdf_the_sources_and_a_manifest(
    client: TestClient, tmp_path: Path
) -> None:
    case_id, document_ids = _ready(client, tmp_path)
    signed = client.post(
        f"/cases/{case_id}/fill-and-sign",
        headers={"X-Office-Client-Ip": _OFFICE_IP, "X-Office-User-Agent": _OFFICE_AGENT},
        json=_SIGN,
    )
    assert signed.status_code == 200, signed.text
    audit = signed.json()["case"]["audit"]

    bundle, manifest, raw = _archive(client, case_id)
    assert sorted(bundle.namelist()) == [
        "bl_6101_signed.pdf",
        "source_documents/bank_confirmation_c-bank.pdf",
        "source_documents/id_copy_a-id.pdf",
        "source_documents/tax_form_b-tax.pdf",
        "verification_manifest.json",
    ]

    # The signed PDF is byte for byte the one on record.
    pdf = bundle.read("bl_6101_signed.pdf")
    assert pdf == client.get(f"/cases/{case_id}/signed-document").content
    assert hashlib.sha256(pdf).hexdigest() == audit["file_sha256"]

    assert raw.startswith("{\n  ")
    assert manifest["case_id"] == case_id
    assert manifest["process_type"] == "onboarding"
    assert manifest["status"] == "signed"
    assert manifest["exported_at"]
    seal = manifest["signature_seal"]
    assert set(seal) == {"verification_id", "signed_at", "signed_pdf_sha256", "review_digest"}
    assert seal["verification_id"] == audit["signer_verification_id"]
    assert seal["signed_pdf_sha256"] == audit["file_sha256"]
    assert seal["signed_at"].startswith(audit["signed_at"][:19])
    assert len(seal["review_digest"]) == 64
    assert manifest["form_pdf"] == {
        "archive_path": "bl_6101_signed.pdf",
        "kind": "signed",
        "sha256": audit["file_sha256"],
    }

    # Every source file is present once and hashes to what the manifest says.
    listed = manifest["documents"]
    assert {item["id"] for item in listed} == set(document_ids)
    for item in listed:
        data = bundle.read(item["archive_path"])
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
        assert item["sha256"] == item["upload_sha256"]
        assert item["size"] == len(data)
        assert item["role"] == "evidence"
        assert item["archive_path"].startswith(f"source_documents/{item['document_type']}_")
        original = client.get(f"/cases/{case_id}/documents/{item['id']}/file").content
        assert data == original

    trail = manifest["audit_trail"]
    actions = [event["action"] for event in trail]
    assert "manual_classify" in actions
    assert "fill_and_sign" in actions
    assert actions[-1] == "archive_exported"
    signing = next(event for event in trail if event["action"] == "fill_and_sign")
    assert signing["details"]["signer_verification_id"] == audit["signer_verification_id"]
    assert signing["details"]["file_sha256"] == audit["file_sha256"]
    assert set(signing["details"]) & {"ip", "user_agent", "output_path"} == set()

    # Nothing personal reaches the manifest: no address, browser, typed value or storage path.
    for secret in (_OFFICE_IP, _OFFICE_AGENT, "Dana Cohen", "123456782", "dana@example.com", "org/"):
        assert secret not in raw

    # The export is recorded, once per download.
    assert _actions(client, case_id).count("archive_exported") == 1
    _archive(client, case_id)
    recorded = [row for row in _audit_rows(client, case_id) if row.action == "archive_exported"]
    assert len(recorded) == 2
    staff = client.get("/auth/me").json()
    assert recorded[0].actor == f"user:{staff['id']}"
    assert recorded[0].new_value == {
        "status": "signed",
        "documents": 3,
        "form_pdf": "bl_6101_signed.pdf",
        "form_pdf_sha256": audit["file_sha256"],
    }


def test_archive_refuses_a_signed_pdf_that_no_longer_matches_its_hash(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    assert client.post(f"/cases/{case_id}/fill-and-sign", json=_SIGN).status_code == 200

    async def tamper() -> None:
        from app.models.case import Case

        async with session_scope() as session:
            case = await session.get(Case, UUID(case_id))
            assert case is not None
            case.file_sha256 = "0" * 64
            await session.commit()

    client.portal.call(tamper)
    refused = client.get(f"/cases/{case_id}/archive")
    assert refused.status_code >= 400
    assert refused.headers["content-type"] != "application/zip"
    assert "archive_exported" not in _actions(client, case_id)


def test_unsigned_archive_carries_the_draft_only_when_a_form_is_present(client: TestClient, tmp_path: Path) -> None:
    case_id, document_id = _office_form(client, tmp_path)
    plain, manifest, _raw = _archive(client, case_id)
    # Not marked as a form yet: a source file like any other, and no draft.
    assert sorted(plain.namelist()) == [
        "source_documents/evidence_office-secret-form.pdf",
        "verification_manifest.json",
    ]
    assert manifest["signature_seal"] is None
    assert manifest["form_pdf"] is None

    marked = client.put(f"/cases/{case_id}/documents/{document_id}/role", json={"role": "form"})
    assert marked.status_code == 200, marked.text
    bundle, manifest, _raw = _archive(client, case_id)
    assert sorted(bundle.namelist()) == [
        "bl_6101_draft.pdf",
        "source_documents/form_office-secret-form.pdf",
        "verification_manifest.json",
    ]
    draft = bundle.read("bl_6101_draft.pdf")
    assert draft.startswith(b"%PDF")
    assert manifest["status"] != "signed"
    assert manifest["signature_seal"] is None
    assert manifest["form_pdf"] == {
        "archive_path": "bl_6101_draft.pdf",
        "kind": "draft",
        "sha256": hashlib.sha256(draft).hexdigest(),
        "document_id": document_id,
    }
    assert [item["role"] for item in manifest["documents"]] == ["form"]
    assert manifest["documents"][0]["document_type"] in (None, "unknown")
    # The source stays the untouched upload, not the filled copy.
    source = bundle.read("source_documents/form_office-secret-form.pdf")
    assert source == client.get(f"/cases/{case_id}/documents/{document_id}/file").content
    assert source != draft


def test_archive_of_an_empty_case_is_just_the_manifest(client: TestClient) -> None:
    created = client.post("/cases", json={"name": "Empty", "process_key": "onboarding"})
    case_id = created.json()["id"]
    bundle, manifest, _raw = _archive(client, case_id)
    assert bundle.namelist() == ["verification_manifest.json"]
    assert manifest["documents"] == []
    assert manifest["status"] == "draft"
    assert [event["action"] for event in manifest["audit_trail"]] == ["archive_exported"]


def test_source_names_stay_inside_the_folder_and_do_not_collide() -> None:
    taken: set[str] = set()
    assert source_name("id_copy", "scan.pdf", taken) == "source_documents/id_copy_scan.pdf"
    assert source_name("id_copy", "SCAN.pdf", taken) == "source_documents/id_copy_SCAN_2.pdf"
    assert source_name("id_copy", "scan.pdf", taken) == "source_documents/id_copy_scan_3.pdf"
    # Path separators are flattened, so the entry cannot leave its folder.
    assert source_name("evidence", "../../etc/passwd", taken) == "source_documents/evidence__.._etc_passwd"
    assert source_name("evidence", "C:\\Users\\x\\scan.pdf", taken) == "source_documents/evidence_C_Users_x_scan.pdf"
    assert source_name("evidence", "תעודת זהות.pdf", taken) == "source_documents/evidence_תעודת זהות.pdf"
    assert source_name("", "", taken) == "source_documents/document_file"


def test_audit_entries_keep_identifiers_and_drop_personal_details() -> None:
    entry = audit_entry(
        event_id="e1",
        action="manual_classify",
        actor="user:1",
        created_at="2026-11-14T00:00:00+00:00",
        document_id=None,
        previous_value={"document_type": None, "display_title": "Dana's form"},
        new_value={"document_type": "id_copy", "ip": "203.0.113.9", "user_agent": "X", "output_path": "org/x"},
        notes="Dana Cohen's passport",
    )
    assert entry["details"] == {"document_type": "id_copy"}
    assert entry["previous"] == {"document_type": None}
    assert "notes" not in entry
    system = audit_entry(
        event_id="e2",
        action="signature_invalidated",
        actor="user:1",
        created_at=None,
        document_id=None,
        previous_value=None,
        new_value=None,
        notes="A field changed after signing.",
    )
    assert system["notes"] == "A field changed after signing."
    assert system["details"] is None


# Reopen


def test_reopen_unlocks_a_portal_signed_case_and_keeps_its_data(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    created = client.post(f"/cases/{case_id}/signing-links")
    assert created.status_code == 201, created.text
    token = _token(created.json()["url"])
    view = client.get("/portal", headers=_auth(token)).json()
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG, "review_digest": view["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    before = client.get(f"/cases/{case_id}").json()
    seal = before["case"]["audit"]
    assert before["case"]["status"] == "signed"

    # The manifest carries the digest the signer agreed to.
    _bundle, manifest, _raw = _archive(client, case_id)
    assert manifest["signature_seal"]["review_digest"] == view["review_digest"]

    reopened = client.post(f"/cases/{case_id}/reopen")
    assert reopened.status_code == 200, reopened.text
    body = reopened.json()
    assert body["case"]["status"] == "filling"
    assert body["ready_to_sign"] is True
    assert body["signing_blockers"] == []
    assert body["gap"]["pipeline"]["stage"] == "ready_for_signature"
    assert body["case"]["download_ready"] is False
    assert body["case"]["audit"] == {
        "is_signed": False,
        "signed_at": None,
        "signer_verification_id": None,
        "content_sha256": None,
        "file_sha256": None,
        "certificate": None,
    }
    # Everything the case held is still there.
    assert body["field_values"] == before["field_values"]
    assert body["field_sources"] == before["field_sources"]
    assert body["case"]["document_count"] == before["case"]["document_count"]
    assert body["messages"] == before["messages"]

    # The signer's link is dead and the superseded packet is no longer served.
    assert client.get("/portal", headers=_auth(token)).status_code == 410
    assert client.get("/portal/signed-document", headers=_auth(token)).status_code == 410
    assert client.get(f"/cases/{case_id}/signed-document").status_code == 404
    assert client.get(f"/cases/{case_id}/certificate").status_code == 404

    async def links() -> list[tuple[bool, str | None]]:
        async with session_scope() as session:
            found = await session.scalars(select(SigningLink).where(SigningLink.case_id == UUID(case_id)))
            return [(row.revoked_at is not None, row.revoke_reason) for row in found]

    assert client.portal.call(links) == [(True, "case_reopened")]

    rows = _audit_rows(client, case_id)
    record = next(row for row in rows if row.action == "case_reopened")
    staff = client.get("/auth/me").json()
    assert record.actor == f"user:{staff['id']}"
    assert record.previous_value["superseded_verification_id"] == seal["signer_verification_id"]
    assert record.previous_value["superseded_signed_pdf_sha256"] == seal["file_sha256"]
    assert record.previous_value["superseded_content_sha256"] == seal["content_sha256"]
    assert record.previous_value["status"] == "signed"
    assert record.new_value == {"status": "filling", "revoked_links": 1}
    # The superseded packet is kept in storage where the audit row says it is.
    stored = client.portal.call(client.app.state.container.store.download_file, record.previous_value["output_path"])
    assert hashlib.sha256(stored).hexdigest() == seal["file_sha256"]

    # A second reopen has nothing to unlock.
    again = client.post(f"/cases/{case_id}/reopen")
    assert again.status_code == 409, again.text

    # The correction: an ordinary field edit, with no signature left to invalidate.
    edited = client.post(f"/cases/{case_id}/fields", json={"key": "full_name", "value": "Dana Levi"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["field_values"]["full_name"] == "Dana Levi"
    assert edited.json()["ready_to_sign"] is True
    actions = _actions(client, case_id)
    assert actions.count("case_reopened") == 1
    assert "signature_invalidated" not in actions

    # It can be signed again, as a new packet with a new record.
    resigned = client.post(f"/cases/{case_id}/fill-and-sign", json=_SIGN)
    assert resigned.status_code == 200, resigned.text
    fresh = resigned.json()["case"]["audit"]
    assert fresh["signer_verification_id"] != seal["signer_verification_id"]
    assert fresh["file_sha256"] != seal["file_sha256"]

    bundle, manifest, raw = _archive(client, case_id)
    assert hashlib.sha256(bundle.read("bl_6101_signed.pdf")).hexdigest() == fresh["file_sha256"]
    assert manifest["signature_seal"]["verification_id"] == fresh["signer_verification_id"]
    assert manifest["signature_seal"]["review_digest"] != view["review_digest"]
    trail = manifest["audit_trail"]
    order = [event["action"] for event in trail]
    assert order.index("case_reopened") < len(order) - 1 - order[::-1].index("fill_and_sign")
    event = next(item for item in trail if item["action"] == "case_reopened")
    assert event["previous"] == {
        "status": "signed",
        "superseded_verification_id": seal["signer_verification_id"],
        "superseded_signed_pdf_sha256": seal["file_sha256"],
        "superseded_content_sha256": seal["content_sha256"],
        "superseded_signed_at": event["previous"]["superseded_signed_at"],
        "case_reference": event["previous"]["case_reference"],
    }
    assert event["details"] == {"status": "filling", "revoked_links": 1}
    assert "Dana Levi" not in raw and "org/" not in raw


def test_reopen_after_office_signing_allows_a_new_signing_link(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    assert client.post(f"/cases/{case_id}/fill-and-sign", json=_SIGN).status_code == 200
    assert client.post(f"/cases/{case_id}/signing-links").status_code == 409
    reopened = client.post(f"/cases/{case_id}/reopen")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["case"]["status"] == "filling"
    link = client.post(f"/cases/{case_id}/signing-links")
    assert link.status_code == 201, link.text
    view = client.get("/portal", headers=_auth(_token(link.json()["url"])))
    assert view.status_code == 200, view.text
    assert view.json()["state"] == "open"
    assert view.json()["ready_to_sign"] is True


def test_reopen_is_refused_unless_the_case_is_signed(client: TestClient, tmp_path: Path) -> None:
    empty = client.post("/cases", json={"name": "Empty", "process_key": "onboarding"}).json()["id"]
    assert client.post(f"/cases/{empty}/reopen").status_code == 409

    case_id, _ = _ready(client, tmp_path)
    before = client.get(f"/cases/{case_id}").json()
    refused = client.post(f"/cases/{case_id}/reopen")
    assert refused.status_code == 409, refused.text
    after = client.get(f"/cases/{case_id}").json()
    assert after["case"]["status"] == before["case"]["status"]
    assert after["field_values"] == before["field_values"]
    assert "case_reopened" not in _actions(client, case_id)
    # An open link survives a refused reopen.
    link = client.post(f"/cases/{case_id}/signing-links")
    token = _token(link.json()["url"])
    assert client.post(f"/cases/{case_id}/reopen").status_code == 409
    assert client.get("/portal", headers=_auth(token)).status_code == 200


# Tenancy


def test_another_organization_cannot_export_or_reopen(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    assert client.post(f"/cases/{case_id}/fill-and-sign", json=_SIGN).status_code == 200
    before = client.get(f"/cases/{case_id}").json()
    rows_before = len(_audit_rows(client, case_id))
    headers = _other_office(client)

    export = client.get(f"/cases/{case_id}/archive", headers=headers)
    assert export.status_code == 404, export.text
    assert export.headers["content-type"] != "application/zip"
    assert b"PK" not in export.content[:2]
    reopen = client.post(f"/cases/{case_id}/reopen", headers=headers)
    assert reopen.status_code == 404, reopen.text
    for response in (export, reopen):
        assert response.json() == client.get(f"/cases/{UUID(int=0)}/archive").json()

    # No session at all is refused before the case is looked up.
    with TestClient(client.app) as anonymous:
        assert anonymous.get(f"/cases/{case_id}/archive").status_code == 401
        assert anonymous.post(f"/cases/{case_id}/reopen").status_code == 401

    after = client.get(f"/cases/{case_id}").json()
    assert after == before
    assert after["case"]["status"] == "signed"
    assert len(_audit_rows(client, case_id)) == rows_before

    # The other office's own case exports only its own content.
    own = client.post("/cases", headers=headers, json={"name": "Theirs", "process_key": "onboarding"}).json()["id"]
    theirs = client.get(f"/cases/{own}/archive", headers=headers)
    assert theirs.status_code == 200
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(theirs.content)).read("verification_manifest.json"))
    assert manifest["case_id"] == own
    assert manifest["documents"] == []
    assert case_id not in theirs.content.decode("latin-1")
