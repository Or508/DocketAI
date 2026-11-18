"""Form 101 end to end: load the blank, read the documents, preview, sign, verify."""

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

import pymupdf
from fastapi.testclient import TestClient

from app.catalog.processes import PROCESSES
from app.core.config import get_settings
from app.domain.text_layout import contains_hebrew
from app.schemas.process import FieldSpec
from app.services.flat_form import FlatProfile, read_flat_anchors, signature_box
from app.services.fonts import resolve_hebrew_font
from app.services.form101 import build_form_101
from app.services.pdf_filler import _readback_matches
from tests.support import SignedOut, authenticate
from tests.test_bl6101_sanity_drill import _ID, _PNG_B64, _auth, _classify, _pdf, _set, _sign_body, _token, _upload

_KEY = "employee_onboarding"
_SEED = next(process for process in PROCESSES if process.key == _KEY)
_FIELDS = [FieldSpec.model_validate(item) for item in _SEED.required_fields]
_PROFILE = FlatProfile.from_layout(_SEED.layout)
_SLOTS = [
    "national_id",
    "first_name",
    "last_name",
    "city",
    "street",
    "house_number",
    "phone",
    "bank_name",
    "bank_branch",
    "bank_account",
]
_FROM_DOCUMENTS = {
    "national_id": _ID,
    "first_name": "דנה",
    "last_name": "כהן",
    "street": "הרצל",
    "city": "תל אביב",
    "bank_name": "לאומי",
    "bank_branch": "800",
    "bank_account": "456789",
}
_TYPED = {"house_number": "15", "phone": "0501234567"}
_VALUES = {**_FROM_DOCUMENTS, **_TYPED}
_DOCUMENTS = {
    "id.pdf": ("id_copy", ["שם פרטי: דנה", "שם משפחה: כהן", _ID]),
    "arnona.pdf": ("proof_of_address", ["רחוב", "הרצל", "עיר", "תל אביב"]),
    "bank.pdf": ("bank_confirmation", ["שם הבנק: לאומי", "מספר סניף", "800", "מספר חשבון", "456789"]),
}
_TITLE = "טופס 101 – כרטיס עובד ובקשה להקלה ולתיאום מס"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    # No office copy of either blank: Form 101 is drawn, BL/6101 is absent.
    monkeypatch.setenv("FORM_101_TEMPLATE_PATH", str(tmp_path / "server" / "form_101.pdf"))
    monkeypatch.setenv("BL_6101_TEMPLATE_PATH", str(tmp_path / "server" / "bl_6101.pdf"))
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


def _blank() -> bytes:
    font = resolve_hebrew_font(None)
    assert font is not None
    return build_form_101(font)


def _open(client: TestClient, headers: dict[str, str] | None = None) -> str:
    created = client.post(
        "/cases", headers=headers, json={"name": "Form 101", "process_key": _KEY, "client_name": "דנה כהן"}
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _load(client: TestClient, case_id: str) -> dict:
    loaded = client.post(f"/cases/{case_id}/load-default-form")
    assert loaded.status_code == 200, loaded.text
    return loaded.json()


def _forms(client: TestClient, case_id: str) -> list[dict]:
    return client.get(f"/cases/{case_id}/intake").json()["forms"]


def _timeline(client: TestClient, case_id: str) -> list[dict]:
    return client.get(f"/cases/{case_id}/timeline").json()


def _file_documents(client: TestClient, case_id: str, tmp_path: Path) -> dict:
    body: dict = {}
    for name, (document_type, lines) in _DOCUMENTS.items():
        document_id = _upload(client, case_id, name, _pdf(tmp_path / name, lines))
        body = _classify(client, case_id, document_id, document_type)
    return body


def _prepared(client: TestClient, tmp_path: Path) -> tuple[str, str]:
    """A Form 101 case with the blank loaded, the three documents read, and the rest typed."""
    case_id = _open(client)
    _load(client, case_id)
    _file_documents(client, case_id, tmp_path)
    for key, value in _TYPED.items():
        _set(client, case_id, key, value)
    return case_id, _forms(client, case_id)[0]["document_id"]


def _assert_filled(pdf: bytes, tmp_path: Path) -> pymupdf.Document:
    """Every value stands in the cell the blank draws for it."""
    blank = tmp_path / "blank-for-anchors.pdf"
    blank.write_bytes(_blank())
    anchors = {anchor["slot_key"]: anchor for anchor in read_flat_anchors(blank, _FIELDS, _PROFILE)}
    document = pymupdf.open(stream=pdf, filetype="pdf")
    for key, value in _VALUES.items():
        anchor = anchors[key]
        page = document[anchor["page"]]
        rect = pymupdf.Rect(anchor["rect"])
        if anchor["target"] == "comb":
            words = sorted(page.get_text("words", clip=rect), key=lambda word: word[0])
            assert "".join(word[4] for word in words) == value, key
        else:
            assert _readback_matches(value, page.get_text("text", clip=rect), contains_hebrew(value)), key
    return document


# The blank


def test_the_blank_is_drawn_the_same_every_time_and_anchors_every_slot(tmp_path: Path) -> None:
    first, second = _blank(), _blank()
    assert first == second
    assert first.startswith(b"%PDF")
    path = tmp_path / "form_101.pdf"
    path.write_bytes(first)

    document = pymupdf.open(path)
    try:
        assert document.page_count == 2
        assert not any(page.first_widget for page in document)
        # The bottom margin stays blank on both pages, for the audit line of a signed copy.
        for page in document:
            assert not page.get_text("text", clip=pymupdf.Rect(0, page.rect.height - 36, page.rect.width, page.rect.height)).strip()
    finally:
        document.close()

    anchors = read_flat_anchors(path, _FIELDS, _PROFILE)
    assert sorted(anchor["slot_key"] for anchor in anchors) == sorted(_SLOTS)
    by_key = {anchor["slot_key"]: anchor for anchor in anchors}
    assert all(anchor["page"] == 0 and anchor["kind"] == "flat" for anchor in anchors)
    assert by_key["national_id"]["target"] == "comb"
    assert len(by_key["national_id"]["boxes"]) == 9
    assert {anchor["target"] for key, anchor in by_key.items() if key != "national_id"} == {"cell_below"}
    # One signature cell, on the declaration page.
    page, rect = signature_box(path, _SEED.layout["signature_labels"])
    assert page == 1
    assert rect[2] - rect[0] > 150 and rect[3] - rect[1] > 40


# Loading


def test_loading_the_default_form_puts_form_101_on_the_case(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    body = _load(client, case_id)
    assert body["case"]["document_count"] == 1
    assert body["case"]["status"] != "processing"
    assert body["gap"]["unrecognized"] == [] and body["gap"]["in_progress"] == []

    forms = _forms(client, case_id)
    assert [(item["filename"], item["role"]) for item in forms] == [("form_101_official.pdf", "form")]
    assert forms[0]["bound"] == len(_SLOTS)
    document_id = forms[0]["document_id"]
    stored = client.get(f"/cases/{case_id}/documents/{document_id}/file").content
    assert stored == _blank()
    # The server keeps its drawn copy beside the other generated templates.
    from app.services.form101 import FORM_101_VERSION

    assert [path.name for path in (tmp_path / "templates").glob("form-101-blank-v*.pdf")] == [f"form-101-blank-v{FORM_101_VERSION}.pdf"]

    record = next(event for event in _timeline(client, case_id) if event["action"] == "default_form_loaded")
    staff = client.get("/auth/me").json()
    assert record["actor"] == f"user:{staff['id']}"
    assert record["document_id"] == document_id
    assert record["metadata"]["role"] == "form"
    assert record["metadata"]["sha256"] == hashlib.sha256(stored).hexdigest()

    # Loading again changes nothing.
    _load(client, case_id)
    assert [item["document_id"] for item in _forms(client, case_id)] == [document_id]
    actions = [event["action"] for event in _timeline(client, case_id)]
    assert actions.count("default_form_loaded") == 1


def test_an_office_copy_of_form_101_is_used_in_place_of_the_drawn_one(client: TestClient, tmp_path: Path) -> None:
    supplied = tmp_path / "server" / "form_101.pdf"
    supplied.parent.mkdir(parents=True, exist_ok=True)
    document = pymupdf.open(stream=_blank(), filetype="pdf")
    document.set_metadata({"title": "The office's own Form 101"})
    document.save(supplied)
    document.close()
    assert supplied.read_bytes() != _blank()

    case_id = _open(client)
    _load(client, case_id)
    form = _forms(client, case_id)[0]
    assert form["bound"] == len(_SLOTS)
    assert client.get(f"/cases/{case_id}/documents/{form['document_id']}/file").content == supplied.read_bytes()


def test_loading_is_refused_where_there_is_no_form_to_load(client: TestClient, tmp_path: Path) -> None:
    # A process the server has no blank for has nothing to load.
    from app.services.default_forms import default_form

    assert default_form("no_such_process", get_settings()) is None

    # BL/6101 still needs its official blank, and says which setting names it.
    insured = client.post("/cases", json={"name": "BL", "process_key": "bl_6101"}).json()["id"]
    missing = client.post(f"/cases/{insured}/load-default-form")
    assert missing.status_code == 404, missing.text
    assert "BL_6101_TEMPLATE_PATH" in missing.json()["detail"]

    # A signed Form 101 case keeps the form it was signed on.
    case_id, form_id = _prepared(client, tmp_path)
    assert client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body()).status_code == 200
    assert client.post(f"/cases/{case_id}/load-default-form").status_code == 409
    assert [item["document_id"] for item in _forms(client, case_id)] == [form_id]

    # Another office cannot load a form onto this case.
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    assert client.post(f"/cases/{case_id}/load-default-form", headers=headers).status_code == 404
    with SignedOut(client) as anonymous:
        assert anonymous.post(f"/cases/{case_id}/load-default-form").status_code == 401
    theirs = _open(client, headers)
    loaded = client.post(f"/cases/{theirs}/load-default-form", headers=headers)
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["case"]["document_count"] == 1


# Reading the documents


def test_the_id_the_arnona_bill_and_the_bank_letter_fill_the_form_101_slots(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client)
    _load(client, case_id)
    body = _file_documents(client, case_id, tmp_path)
    for key, value in _FROM_DOCUMENTS.items():
        assert body["field_values"][key] == value, key
        assert body["field_sources"][key]["source"] == "document", key
    # Nothing reads a phone or a house number here: a person types them.
    assert "phone" not in body["field_values"] and "house_number" not in body["field_values"]
    assert body["gap"]["missing"] == []
    assert body["ready_to_sign"] is False

    # Each group of details names the one file it was read from.
    sources = body["field_sources"]
    groups = [("national_id", "first_name", "last_name"), ("street", "city"), ("bank_name", "bank_branch", "bank_account")]
    files = [{sources[key]["document_id"] for key in group} for group in groups]
    assert all(len(found) == 1 and None not in found for found in files)
    assert len(set().union(*files)) == 3

    for key, value in _TYPED.items():
        body = _set(client, case_id, key, value)
        assert body["field_sources"][key]["source"] == "office"
    assert body["field_values"] == _VALUES
    assert body["ready_to_sign"] is True, body["signing_blockers"]


# Preview


def test_the_preview_shows_every_value_in_its_cell_as_a_draft(client: TestClient, tmp_path: Path) -> None:
    case_id, form_id = _prepared(client, tmp_path)
    report = client.get(f"/cases/{case_id}/documents/{form_id}/fill-report")
    assert report.status_code == 200, report.text

    preview = client.get(f"/cases/{case_id}/documents/{form_id}/filled-preview")
    assert preview.status_code == 200, preview.text
    document = _assert_filled(preview.content, tmp_path)
    try:
        assert document.page_count == 2
        # The office copy is marked as a draft in Hebrew, whichever way the letters are extracted.
        shown = " ".join(page.get_text() for page in document)
        assert "טיוטה" in shown or "הטויט" in shown
        # No signature yet: nothing is drawn in the signature cell.
        assert document[1].get_image_info() == []
    finally:
        document.close()
    # The stored blank is never written to.
    assert client.get(f"/cases/{case_id}/documents/{form_id}/file").content == _blank()

    token = _token(client, case_id)
    signer = client.get("/portal/preview", headers=_auth(token))
    assert signer.status_code == 200, signer.text
    seen = _assert_filled(signer.content, tmp_path)
    try:
        assert "DRAFT - NOT SIGNED" in " ".join(page.get_text() for page in seen)
    finally:
        seen.close()


# Signing


def test_the_employee_signs_through_the_link_and_the_seal_verifies(client: TestClient, tmp_path: Path) -> None:
    case_id, form_id = _prepared(client, tmp_path)
    token = _token(client, case_id)
    view = client.get("/portal", headers=_auth(token)).json()
    assert view["ready_to_sign"] is True
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG_B64, "review_digest": view["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text

    office = client.get(f"/cases/{case_id}").json()
    assert office["case"]["status"] == "signed"
    seal = office["case"]["audit"]
    assert seal["signer_verification_id"].startswith("DV-")
    packet = client.get(f"/cases/{case_id}/signed-document").content
    assert hashlib.sha256(packet).hexdigest() == seal["file_sha256"]
    assert client.get("/portal/signed-document", headers=_auth(token)).content == packet

    document = _assert_filled(packet, tmp_path)
    try:
        # The two form pages, then the certificate page.
        assert document.page_count == 3
        assert "DRAFT" not in "".join(page.get_text() for page in document)
        blank = tmp_path / "blank-for-signature.pdf"
        blank.write_bytes(_blank())
        page_index, rect = signature_box(blank, _SEED.layout["signature_labels"])
        assert page_index == 1
        box = pymupdf.Rect(rect)
        placed = [pymupdf.Rect(item["bbox"]) for item in document[1].get_image_info()]
        assert placed and all(box.contains(item) or (box & item).get_area() > 0.9 * item.get_area() for item in placed)
        assert document[0].get_image_info() == []
        certificate = document[2].get_text()
        assert seal["signer_verification_id"] in certificate
        # Every page carries the audit line with the content digest.
        assert all(seal["content_sha256"] in page.get_text().replace("\n", "") for page in document)
    finally:
        document.close()

    with SignedOut(client) as anonymous:
        verified = anonymous.get(
            f"/verify/{seal['signer_verification_id']}", params={"sha256": hashlib.sha256(packet).hexdigest()}
        )
    assert verified.status_code == 200, verified.text
    assert verified.json()["valid"] is True
    assert verified.json()["process_type"] == _KEY
    assert verified.json()["hash_matches"] is True
    assert verified.json()["masked_client_name"] == "דנה כ."

    events = [event["action"] for event in _timeline(client, case_id)]
    assert events.index("default_form_loaded") < events.index("fill_and_sign")


def test_the_office_can_sign_form_101_at_the_desk_and_reopen_it(client: TestClient, tmp_path: Path) -> None:
    case_id, form_id = _prepared(client, tmp_path)
    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert signed.status_code == 200, signed.text
    assert signed.json()["case"]["status"] == "signed"
    packet = client.get(f"/cases/{case_id}/signed-document").content
    document = _assert_filled(packet, tmp_path)
    try:
        assert document.page_count == 3
        assert document[1].get_image_info() != []
    finally:
        document.close()

    reopened = client.post(f"/cases/{case_id}/reopen")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["field_values"] == _VALUES
    assert reopened.json()["ready_to_sign"] is True
    assert [item["document_id"] for item in _forms(client, case_id)] == [form_id]


def test_signing_is_blocked_until_the_form_is_on_the_case(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    _file_documents(client, case_id, tmp_path)
    for key, value in _TYPED.items():
        _set(client, case_id, key, value)
    # Every detail is in place, but there is no form to write them on.
    assert _forms(client, case_id) == []
    assert client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body()).status_code >= 400
    assert client.get(f"/cases/{case_id}").json()["case"]["status"] != "signed"
    ready = _load(client, case_id)
    assert ready["ready_to_sign"] is True, ready["signing_blockers"]
    assert ready["field_values"] == _VALUES


# Catalog


def test_the_catalog_lists_form_101_as_ready_with_its_fields_and_sources(client: TestClient) -> None:
    response = client.get("/templates")
    assert response.status_code == 200, response.text
    listed = response.json()
    assert [item["process_type"] for item in listed][:4] == ["bl_6101", "onboarding", "real_estate", _KEY]
    form = next(item for item in listed if item["process_type"] == _KEY)
    assert form["title_he"] == _TITLE
    assert form["description_he"]
    assert form["form_source"] == "official_blank"
    assert form["default_template_available"] is True
    # BL/6101 has no blank on this server, and says so.
    assert next(item for item in listed if item["process_type"] == "bl_6101")["default_template_available"] is False

    assert [item["id"] for item in form["required_drawers"]] == ["id_copy", "proof_of_address", "bank_confirmation"]
    fields = {item["key"]: item for item in form["mapped_fields"]}
    assert list(fields) == _SLOTS
    assert fields["national_id"]["target"] == {"page": 1, "mode": "digit_boxes", "section_he": "פרטי העובד"}
    assert {item["target"]["mode"] for key, item in fields.items() if key != "national_id"} == {"text"}
    assert {item["target"]["page"] for item in fields.values()} == {1}
    assert fields["street"]["target"]["section_he"] == "כתובת מגורים ופרטי התקשרות"
    assert fields["national_id"]["sources"] == [{"drawer_id": "id_copy", "label_he": "תעודת זהות"}]
    assert fields["city"]["sources"] == [{"drawer_id": "proof_of_address", "label_he": "חשבון ארנונה"}]
    assert fields["bank_branch"]["sources"] == [{"drawer_id": "bank_confirmation", "label_he": "אישור בנק"}]
    assert fields["phone"]["sources"] == []
    assert fields["house_number"]["required"] is False
    assert form["case_counts"] == {"total": 0, "filling": 0, "signed": 0}

    _open(client)
    counted = next(item for item in client.get("/templates").json() if item["process_type"] == _KEY)
    assert counted["case_counts"] == {"total": 1, "filling": 1, "signed": 0}
