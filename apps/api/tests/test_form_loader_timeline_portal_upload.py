"""The server's own BL/6101, the audit timeline, and documents sent through the signing link."""

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.archive import timeline_metadata
from tests.support import SignedOut, authenticate
from tests.test_bl6101_sanity_drill import (
    _ID,
    _VALUES,
    _auth,
    _bl_form,
    _open,
    _pdf,
    _ready,
    _set,
    _sign_body,
    _sources,
    _token,
)

_PNG_B64 = _sign_body()["signature_png_base64"]
_ID_LINES = [f"שם פרטי: {_VALUES['first_name']}", f"שם משפחה: {_VALUES['last_name']}", _ID]


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("BL_6101_TEMPLATE_PATH", str(tmp_path / "server" / "official.pdf"))
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


def _server_form(tmp_path: Path) -> bytes:
    path = tmp_path / "server" / "official.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    return _bl_form(path).read_bytes()


def _other_office(client: TestClient) -> dict[str, str]:
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    return {"Authorization": f"Bearer {other['token']}"}


def _forms(client: TestClient, case_id: str) -> list[dict]:
    return client.get(f"/cases/{case_id}/intake").json()["forms"]


def _timeline(client: TestClient, case_id: str) -> list[dict]:
    response = client.get(f"/cases/{case_id}/timeline")
    assert response.status_code == 200, response.text
    return response.json()


def _send(client: TestClient, token: str, name: str, data: bytes, document_type: str, **extra: str):
    return client.post(
        "/portal/documents",
        headers=_auth(token),
        files={"file": (name, data, "application/pdf")},
        data={"document_type": document_type, **extra},
    )


def _waiting_case(client: TestClient, tmp_path: Path) -> tuple[str, str]:
    """A BL/6101 case with its three drawers filled by blank slips and a marked form, but no details."""
    case_id = _open(client)
    _sources(client, case_id, tmp_path)
    form = _bl_form(tmp_path / "desk-form.pdf").read_bytes()
    uploaded = client.post(
        f"/cases/{case_id}/upload",
        files=[("files", ("desk-form.pdf", form, "application/pdf"))],
        data={"role": "form"},
    )
    assert uploaded.status_code == 200, uploaded.text
    return case_id, _token(client, case_id)


# Default form


def test_missing_server_form_is_a_clear_404_and_changes_nothing(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    before = client.get(f"/cases/{case_id}").json()
    missing = client.post(f"/cases/{case_id}/load-default-form")
    assert missing.status_code == 404, missing.text
    assert "BL_6101_TEMPLATE_PATH" in missing.json()["detail"]
    assert client.get(f"/cases/{case_id}").json() == before
    assert _timeline(client, case_id) == []


def test_the_fallback_path_is_the_repository_test_file(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import Settings
    from app.core.paths import REPO_ROOT

    monkeypatch.setenv("BL_6101_TEMPLATE_PATH", "")
    assert Settings().resolved_bl_6101_template == REPO_ROOT / "test_files_for_browser" / "bl_6101_official.pdf"
    monkeypatch.setenv("BL_6101_TEMPLATE_PATH", "C:/forms/blank.pdf")
    assert Settings().resolved_bl_6101_template == Path("C:/forms/blank.pdf")


def test_loading_puts_the_server_form_on_the_case_with_its_anchors(client: TestClient, tmp_path: Path) -> None:
    official = _server_form(tmp_path)
    case_id = _open(client)
    loaded = client.post(f"/cases/{case_id}/load-default-form")
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    assert body["case"]["document_count"] == 1
    assert body["case"]["status"] != "processing"
    assert body["gap"]["unrecognized"] == []
    assert body["gap"]["in_progress"] == []

    forms = _forms(client, case_id)
    assert [(item["filename"], item["role"]) for item in forms] == [("bl_6101_official.pdf", "form")]
    # read_flat_anchors bound the printed labels to the process slots.
    assert forms[0]["bound"] >= len(_VALUES)
    document_id = forms[0]["document_id"]
    stored = client.get(f"/cases/{case_id}/documents/{document_id}/file").content
    assert stored == official

    events = _timeline(client, case_id)
    record = next(event for event in events if event["action"] == "default_form_loaded")
    staff = client.get("/auth/me").json()
    assert record["actor"] == f"user:{staff['id']}"
    assert record["document_id"] == document_id
    assert record["metadata"]["role"] == "form"
    assert record["metadata"]["sha256"] == hashlib.sha256(official).hexdigest()

    # Loading it again changes nothing.
    again = client.post(f"/cases/{case_id}/load-default-form")
    assert again.status_code == 200, again.text
    assert [item["document_id"] for item in _forms(client, case_id)] == [document_id]
    actions = [event["action"] for event in _timeline(client, case_id)]
    assert actions.count("default_form_loaded") == 1


def test_loading_replaces_the_form_the_case_had_and_keeps_its_evidence(client: TestClient, tmp_path: Path) -> None:
    _server_form(tmp_path)
    case_id = _open(client)
    _sources(client, case_id, tmp_path)
    kept = _set(client, case_id, "phone", _VALUES["phone"])
    assert kept["field_sources"]["phone"]["source"] == "office"
    old = _bl_form(tmp_path / "old-form.pdf", copy_mark="OLD COPY").read_bytes()
    uploaded = client.post(
        f"/cases/{case_id}/upload",
        files=[("files", ("old-form.pdf", old, "application/pdf"))],
        data={"role": "form"},
    )
    assert uploaded.status_code == 200, uploaded.text
    old_id = _forms(client, case_id)[0]["document_id"]

    loaded = client.post(f"/cases/{case_id}/load-default-form")
    assert loaded.status_code == 200, loaded.text
    body = loaded.json()
    forms = _forms(client, case_id)
    assert [(item["filename"], item["role"]) for item in forms] == [("bl_6101_official.pdf", "form")]
    assert forms[0]["document_id"] != old_id
    assert body["case"]["document_count"] == 4
    assert body["field_values"]["phone"] == _VALUES["phone"]
    assert body["gap"]["missing"] == []
    assert client.get(f"/cases/{case_id}/documents/{old_id}/file").status_code == 404

    events = _timeline(client, case_id)
    removed = [event for event in events if event["action"] == "document_removed"]
    assert [event["metadata"]["document_id"] for event in removed] == [old_id]
    assert removed[0]["metadata"]["sha256"] == hashlib.sha256(old).hexdigest()
    assert [event["action"] for event in events][-1] == "default_form_loaded"

    # The case signs on the loaded form.
    for key, value in _VALUES.items():
        _set(client, case_id, key, value)
    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert signed.status_code == 200, signed.text
    assert signed.json()["case"]["status"] == "signed"


def test_a_server_file_that_is_not_a_pdf_is_refused_and_keeps_the_old_form(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    old = _bl_form(tmp_path / "old-form.pdf").read_bytes()
    client.post(
        f"/cases/{case_id}/upload",
        files=[("files", ("old-form.pdf", old, "application/pdf"))],
        data={"role": "form"},
    )
    before = _forms(client, case_id)
    path = tmp_path / "server" / "official.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not a form")
    refused = client.post(f"/cases/{case_id}/load-default-form")
    assert refused.status_code == 409, refused.text
    assert _forms(client, case_id) == before


def test_loading_is_refused_on_a_signed_case_and_on_another_process(client: TestClient, tmp_path: Path) -> None:
    _server_form(tmp_path)
    case_id, form_id = _ready(client, tmp_path)
    assert client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body()).status_code == 200
    before = client.get(f"/cases/{case_id}").json()
    refused = client.post(f"/cases/{case_id}/load-default-form")
    assert refused.status_code == 409, refused.text
    after = client.get(f"/cases/{case_id}").json()
    assert after == before
    assert after["case"]["status"] == "signed"
    assert [item["document_id"] for item in _forms(client, case_id) if item["role"] == "form"] == [form_id]

    # Every process in the catalog now has a blank of its own: another process loads its own form.
    deal = client.post("/cases", json={"name": "Deal", "process_key": "real_estate"}).json()["id"]
    other = client.post(f"/cases/{deal}/load-default-form")
    assert other.status_code == 200, other.text
    assert other.json()["case"]["document_count"] == 1


# Timeline


def test_timeline_lists_the_case_events_in_order_without_personal_details(client: TestClient, tmp_path: Path) -> None:
    case_id, form_id = _ready(client, tmp_path)
    signed = client.post(
        f"/cases/{case_id}/fill-and-sign",
        headers={"X-Office-Client-Ip": "203.0.113.9", "X-Office-User-Agent": "OfficeBrowser/9"},
        json=_sign_body(),
    )
    assert signed.status_code == 200, signed.text
    seal = signed.json()["case"]["audit"]
    assert client.post(f"/cases/{case_id}/reopen").status_code == 200

    response = client.get(f"/cases/{case_id}/timeline")
    assert response.status_code == 200, response.text
    events = response.json()
    assert all(set(event) == {"id", "action", "actor", "created_at", "document_id", "metadata"} for event in events)
    stamps = [event["created_at"] for event in events]
    assert stamps == sorted(stamps)
    assert len({event["id"] for event in events}) == len(events)
    actions = [event["action"] for event in events]
    assert actions[-2:] == ["fill_and_sign", "case_reopened"]
    assert "manual_classify" in actions and "document_role_changed" in actions

    classified = next(event for event in events if event["action"] == "manual_classify")
    assert classified["document_id"]
    assert classified["metadata"]["document_type"] in {"id_copy", "proof_of_address", "bank_confirmation"}
    marked = next(event for event in events if event["action"] == "document_role_changed")
    assert marked["document_id"] == form_id
    assert marked["metadata"]["role"] == "form"
    signing = events[-2]
    assert signing["metadata"]["verification_id"] == seal["signer_verification_id"]
    assert signing["metadata"]["sha256"] == seal["file_sha256"]
    assert signing["metadata"]["form_document_id"] == form_id
    reopened = events[-1]
    assert reopened["metadata"]["superseded_verification_id"] == seal["signer_verification_id"]
    assert reopened["metadata"]["superseded_signed_pdf_sha256"] == seal["file_sha256"]
    assert "verification_id" not in reopened["metadata"]

    banned_keys = {"ip", "user_agent", "output_path", "content_path", "display_title", "notes"}
    assert all(not (set(event["metadata"]) & banned_keys) for event in events)
    # Short numbers (a house number, a branch) would match by chance inside an id or a hash.
    typed = [value for value in _VALUES.values() if not (value.isdigit() and len(value) < 7)]
    for secret in ("203.0.113.9", "OfficeBrowser/9", "org/", _ID, *typed):
        assert secret not in response.text

    # Reading the timeline is not itself an event.
    assert client.get(f"/cases/{case_id}/timeline").json() == events


def test_timeline_metadata_names_what_was_set_and_what_was_superseded() -> None:
    signed = timeline_metadata(
        None,
        {"signer_verification_id": "DV-NEW", "file_sha256": "f" * 64, "ip": "203.0.113.9", "user_agent": "X"},
    )
    assert signed["verification_id"] == "DV-NEW"
    assert signed["sha256"] == "f" * 64
    assert "ip" not in signed and "user_agent" not in signed
    invalidated = timeline_metadata(
        {"signer_verification_id": "DV-OLD", "file_sha256": "a" * 64, "output_path": "org/x/signed.pdf"}, None
    )
    assert invalidated == {"superseded_verification_id": "DV-OLD", "superseded_signed_pdf_sha256": "a" * 64}
    removed = timeline_metadata({"document_id": "d1", "document_type": "id_copy", "content_hash": "c" * 64}, None)
    assert removed == {"document_id": "d1", "document_type": "id_copy", "content_hash": "c" * 64, "sha256": "c" * 64}
    assert timeline_metadata(None, None) == {}
    assert timeline_metadata("text", ["list"]) == {}


# Portal upload


def test_a_signer_upload_fills_empty_slots_and_changes_the_digest(client: TestClient, tmp_path: Path) -> None:
    case_id, token = _waiting_case(client, tmp_path)
    opened = client.get("/portal", headers=_auth(token)).json()
    assert "first_name" not in opened["field_values"]
    count = client.get(f"/cases/{case_id}").json()["case"]["document_count"]

    sent = _send(client, token, "my-id.pdf", _pdf(tmp_path / "my-id.pdf", _ID_LINES), "id_card")
    assert sent.status_code == 200, sent.text
    view = sent.json()
    assert set(view) == set(opened)
    assert view["state"] == "open"
    assert view["field_values"]["first_name"] == _VALUES["first_name"]
    assert view["field_values"]["last_name"] == _VALUES["last_name"]
    assert view["field_values"]["national_id"] == _ID
    assert view["review_digest"] != opened["review_digest"]
    assert view["review_digest"] == client.get("/portal", headers=_auth(token)).json()["review_digest"]

    # It took the drawer: the blank slip the office had filed there is gone.
    office = client.get(f"/cases/{case_id}").json()
    assert office["case"]["document_count"] == count
    assert office["case"]["status"] != "processing"
    assert office["gap"]["missing"] == [] and office["gap"]["unrecognized"] == []
    assert office["field_sources"]["first_name"]["source"] == "document"
    events = _timeline(client, case_id)
    upload = next(event for event in events if event["action"] == "client_document_uploaded")
    assert upload["actor"] == "signer"
    assert upload["metadata"]["document_type"] == "id_copy"
    assert office["field_sources"]["first_name"]["document_id"] == upload["document_id"]
    filed = [event for event in events if event["action"] == "manual_classify" and event["actor"] == "signer"]
    assert [event["document_id"] for event in filed] == [upload["document_id"]]
    removed = [event for event in events if event["action"] == "document_removed"]
    assert len(removed) == 1 and removed[0]["metadata"]["document_type"] == "id_copy"
    # The signer never sees office identifiers.
    assert case_id not in sent.text and upload["document_id"] not in sent.text


def test_a_signer_upload_never_replaces_what_the_office_typed(client: TestClient, tmp_path: Path) -> None:
    case_id, token = _waiting_case(client, tmp_path)
    kept = _set(client, case_id, "street", "הרצל 10")
    assert kept["field_sources"]["street"]["source"] == "office"

    bill = _pdf(tmp_path / "bill.pdf", ["רחוב", "הרצל 15", "עיר", "תל אביב"])
    sent = _send(client, token, "bill.pdf", bill, "address_proof")
    assert sent.status_code == 200, sent.text
    assert sent.json()["field_values"]["street"] == "הרצל 10"
    assert sent.json()["field_values"]["city"] == "תל אביב"
    office = client.get(f"/cases/{case_id}").json()
    assert office["field_sources"]["street"] == {"source": "office", "document_id": None}
    assert office["field_sources"]["city"]["source"] == "document"
    conflicts = [item for reading in office["readings"] for item in reading["conflicts"]]
    assert any(item["slot_key"] == "street" for item in conflicts)

    # A newer file in the same drawer replaces what the older one supplied.
    moved = _pdf(tmp_path / "bill-2.pdf", ["רחוב", "הרצל 15", "עיר", "חיפה"])
    again = _send(client, token, "bill-2.pdf", moved, "proof_of_address")
    assert again.status_code == 200, again.text
    assert again.json()["field_values"]["city"] == "חיפה"
    assert again.json()["field_values"]["street"] == "הרצל 10"
    assert again.json()["review_digest"] != sent.json()["review_digest"]


def test_replace_existing_false_keeps_the_file_already_in_the_drawer(client: TestClient, tmp_path: Path) -> None:
    case_id, token = _waiting_case(client, tmp_path)
    count = client.get(f"/cases/{case_id}").json()["case"]["document_count"]
    letter = _pdf(tmp_path / "letter.pdf", ["שם הבנק: לאומי", "מספר סניף", "800", "מספר חשבון", "456789"])
    sent = _send(client, token, "letter.pdf", letter, "bank_confirmation", replace_existing="false")
    assert sent.status_code == 200, sent.text
    assert sent.json()["field_values"]["bank_branch"] == "800"
    assert client.get(f"/cases/{case_id}").json()["case"]["document_count"] == count + 1
    assert "document_removed" not in [event["action"] for event in _timeline(client, case_id)]
    # The same bytes again are not stored twice.
    twice = _send(client, token, "letter.pdf", letter, "bank_confirmation", replace_existing="false")
    assert twice.status_code == 200, twice.text
    assert client.get(f"/cases/{case_id}").json()["case"]["document_count"] == count + 1


def test_a_bad_drawer_or_file_is_refused_and_stores_nothing(client: TestClient, tmp_path: Path) -> None:
    case_id, token = _waiting_case(client, tmp_path)
    before = client.get(f"/cases/{case_id}").json()
    good = _pdf(tmp_path / "x.pdf", _ID_LINES)
    for document_type in ("passport", "form", "", "pension_form"):
        refused = _send(client, token, "x.pdf", good, document_type)
        assert refused.status_code in (400, 422), (document_type, refused.text)
    garbage = _send(client, token, "x.pdf", b"not a pdf at all", "id_card")
    assert garbage.status_code == 400, garbage.text
    assert "x.pdf" in garbage.json()["detail"]
    nothing = client.post("/portal/documents", headers=_auth(token), data={"document_type": "id_card"})
    assert nothing.status_code == 422
    assert client.get(f"/cases/{case_id}").json() == before


def test_signed_revoked_and_unknown_links_cannot_upload(client: TestClient, tmp_path: Path) -> None:
    case_id, form_id = _ready(client, tmp_path)
    token = _token(client, case_id)
    data = _pdf(tmp_path / "late-id.pdf", _ID_LINES)

    unknown = _send(client, "not-a-token", "late-id.pdf", data, "id_card")
    assert unknown.status_code == 404
    bare = client.post(
        "/portal/documents", files={"file": ("late-id.pdf", data, "application/pdf")}, data={"document_type": "id_card"}
    )
    assert bare.status_code in (401, 404)

    view = client.get("/portal", headers=_auth(token)).json()
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG_B64, "review_digest": view["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    before = client.get(f"/cases/{case_id}").json()
    late = _send(client, token, "late-id.pdf", data, "id_card")
    assert late.status_code == 409, late.text
    after = client.get(f"/cases/{case_id}").json()
    assert after == before and after["case"]["status"] == "signed"

    # A reopened case has revoked the link: it is gone, like every other portal route.
    assert client.post(f"/cases/{case_id}/reopen").status_code == 200
    revoked = _send(client, token, "late-id.pdf", data, "id_card")
    assert revoked.status_code == 410, revoked.text
    assert client.get(f"/cases/{case_id}").json()["case"]["document_count"] == before["case"]["document_count"]
    assert form_id in [item["document_id"] for item in _forms(client, case_id)]


# Tenancy


def test_another_organization_cannot_load_a_form_read_the_timeline_or_be_reached_by_a_link(
    client: TestClient, tmp_path: Path
) -> None:
    _server_form(tmp_path)
    case_id, token = _waiting_case(client, tmp_path)
    before = client.get(f"/cases/{case_id}").json()
    events = _timeline(client, case_id)
    headers = _other_office(client)

    load = client.post(f"/cases/{case_id}/load-default-form", headers=headers)
    assert load.status_code == 404, load.text
    read = client.get(f"/cases/{case_id}/timeline", headers=headers)
    assert read.status_code == 404, read.text
    assert "action" not in read.text
    with SignedOut(client) as anonymous:
        assert anonymous.post(f"/cases/{case_id}/load-default-form").status_code == 401
        assert anonymous.get(f"/cases/{case_id}/timeline").status_code == 401
    assert client.get(f"/cases/{case_id}").json() == before
    assert _timeline(client, case_id) == events

    # The other office's own case: its timeline is its own, and our link does not touch it.
    theirs = client.post("/cases", headers=headers, json={"name": "Theirs", "process_key": "bl_6101"}).json()["id"]
    loaded = client.post(f"/cases/{theirs}/load-default-form", headers=headers)
    assert loaded.status_code == 200, loaded.text
    their_events = client.get(f"/cases/{theirs}/timeline", headers=headers).json()
    assert [event["action"] for event in their_events][-1] == "default_form_loaded"
    assert not {event["id"] for event in their_events} & {event["id"] for event in events}
    assert client.get(f"/cases/{theirs}/timeline").status_code == 404

    sent = _send(client, token, "my-id.pdf", _pdf(tmp_path / "my-id.pdf", _ID_LINES), "id_card")
    assert sent.status_code == 200, sent.text
    assert client.get(f"/cases/{theirs}", headers=headers).json()["case"]["document_count"] == 1
    assert client.get(f"/cases/{theirs}/timeline", headers=headers).json() == their_events
