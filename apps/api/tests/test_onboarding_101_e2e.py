"""Onboarding on Form 101, end to end: load the blank, bind its cells, preview, sign, export."""

import hashlib
import io
import json
import zipfile
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
from app.services.form101 import build_onboarding_form_101
from app.services.pdf_filler import _readback_matches
from tests.support import SignedOut, authenticate
from tests.test_bl6101_sanity_drill import _ID, _PNG_B64, _auth, _classify, _pdf, _set, _sign_body, _token, _upload

_KEY = "onboarding"
_SEED = next(process for process in PROCESSES if process.key == _KEY)
_FIELDS = [FieldSpec.model_validate(item) for item in _SEED.required_fields]
_PROFILE = FlatProfile.from_layout(_SEED.layout)
_SLOTS = ["full_name", "national_id", "email", "phone", "address_he", "start_date"]
_TYPED = {
    "full_name": "דנה כהן",
    "national_id": _ID,
    "email": "dana@example.com",
    "phone": "0501234567",
    "address_he": "הרצל 15, תל אביב",
    "start_date": "2026-12-01",
}
_DOCUMENTS = {
    "id.pdf": ("id_copy", "צילום תעודה"),
    "tax.pdf": ("tax_form", "טופס מס"),
    "bank.pdf": ("bank_confirmation", "אישור בנק"),
}


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
    return build_onboarding_form_101(font)


def _open(client: TestClient, key: str = _KEY) -> str:
    created = client.post("/cases", json={"name": "New hire", "process_key": key, "client_name": "דנה כהן"})
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


def _fill(client: TestClient, case_id: str, tmp_path: Path) -> dict:
    """File the three required documents and type the six details."""
    for name, (document_type, line) in _DOCUMENTS.items():
        document_id = _upload(client, case_id, name, _pdf(tmp_path / name, [line]))
        _classify(client, case_id, document_id, document_type)
    body: dict = {}
    for key, value in _TYPED.items():
        body = _set(client, case_id, key, value)
    return body


def _prepared(client: TestClient, tmp_path: Path) -> tuple[str, str, dict[str, str]]:
    """An onboarding case with Form 101 loaded and everything in place. Returns the stored values too."""
    case_id = _open(client)
    _load(client, case_id)
    body = _fill(client, case_id, tmp_path)
    assert body["ready_to_sign"] is True, body["signing_blockers"]
    return case_id, _forms(client, case_id)[0]["document_id"], body["field_values"]


def _assert_filled(pdf: bytes, values: dict[str, str], tmp_path: Path) -> pymupdf.Document:
    """Every value stands in the cell the blank draws for it."""
    blank = tmp_path / "blank-for-anchors.pdf"
    blank.write_bytes(_blank())
    anchors = {anchor["slot_key"]: anchor for anchor in read_flat_anchors(blank, _FIELDS, _PROFILE)}
    document = pymupdf.open(stream=pdf, filetype="pdf")
    for key in _SLOTS:
        value = values[key]
        anchor = anchors[key]
        page = document[anchor["page"]]
        rect = pymupdf.Rect(anchor["rect"])
        if anchor["target"] == "comb":
            words = sorted(page.get_text("words", clip=rect), key=lambda word: word[0])
            assert "".join(word[4] for word in words) == value, key
        else:
            assert _readback_matches(value, page.get_text("text", clip=rect), contains_hebrew(value)), key
    return document


def _archive(client: TestClient, case_id: str) -> tuple[zipfile.ZipFile, dict]:
    response = client.get(f"/cases/{case_id}/archive")
    assert response.status_code == 200, response.text
    bundle = zipfile.ZipFile(io.BytesIO(response.content))
    return bundle, json.loads(bundle.read("verification_manifest.json"))


# The blank


def test_the_onboarding_blank_is_stable_and_has_a_cell_for_every_catalog_field(tmp_path: Path) -> None:
    first, second = _blank(), _blank()
    assert first == second
    path = tmp_path / "form_101.pdf"
    path.write_bytes(first)

    document = pymupdf.open(path)
    try:
        assert document.page_count == 2
        assert not any(page.first_widget for page in document)
        assert "101" in document[0].get_text()
        # The bottom margin stays blank on both pages, for the audit line of a signed copy.
        for page in document:
            strip = pymupdf.Rect(0, page.rect.height - 36, page.rect.width, page.rect.height)
            assert not page.get_text("text", clip=strip).strip()
    finally:
        document.close()

    anchors = {anchor["slot_key"]: anchor for anchor in read_flat_anchors(path, _FIELDS, _PROFILE)}
    assert sorted(anchors) == sorted(spec.key for spec in _FIELDS) == sorted(_SLOTS)
    assert all(anchor["page"] == 0 and anchor["kind"] == "flat" for anchor in anchors.values())
    assert anchors["national_id"]["target"] == "comb"
    assert len(anchors["national_id"]["boxes"]) == 9
    assert {anchor["target"] for key, anchor in anchors.items() if key != "national_id"} == {"cell_below"}
    # One signature cell, on the declaration page.
    page, rect = signature_box(path, _SEED.layout["signature_labels"])
    assert page == 1
    assert rect[2] - rect[0] > 150 and rect[3] - rect[1] > 40


# Loading


def test_loading_the_default_form_puts_form_101_on_an_onboarding_case(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    body = _load(client, case_id)
    assert body["case"]["document_count"] == 1
    assert body["case"]["status"] != "processing"
    # The form is not evidence: it waits in no drawer and needs no type.
    assert body["gap"]["unrecognized"] == [] and body["gap"]["in_progress"] == []
    assert len(body["gap"]["missing"]) == 3

    forms = _forms(client, case_id)
    assert [(item["filename"], item["role"]) for item in forms] == [("form_101_official.pdf", "form")]
    assert forms[0]["bound"] == len(_SLOTS)
    document_id = forms[0]["document_id"]
    stored = client.get(f"/cases/{case_id}/documents/{document_id}/file").content
    assert stored == _blank()
    drawn = sorted(path.name for path in (tmp_path / "templates").glob("form-101-*.pdf"))
    assert drawn == ["form-101-onboarding-blank-v1.pdf"]

    record = next(event for event in _timeline(client, case_id) if event["action"] == "default_form_loaded")
    assert record["document_id"] == document_id
    assert record["metadata"]["role"] == "form"
    assert record["metadata"]["sha256"] == hashlib.sha256(stored).hexdigest()

    # Loading again changes nothing.
    _load(client, case_id)
    assert [item["document_id"] for item in _forms(client, case_id)] == [document_id]
    assert [event["action"] for event in _timeline(client, case_id)].count("default_form_loaded") == 1


def test_the_employee_onboarding_key_loads_its_own_form_101(client: TestClient) -> None:
    case_id = _open(client, "employee_onboarding")
    _load(client, case_id)
    forms = _forms(client, case_id)
    assert [(item["filename"], item["role"]) for item in forms] == [("form_101_official.pdf", "form")]
    assert forms[0]["bound"] == 10


def test_loading_is_refused_for_signed_cases_other_offices_and_strangers(client: TestClient, tmp_path: Path) -> None:
    case_id, form_id, _values = _prepared(client, tmp_path)
    assert client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body()).status_code == 200
    assert client.post(f"/cases/{case_id}/load-default-form").status_code == 409
    assert [item["document_id"] for item in _forms(client, case_id)] == [form_id]

    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    assert client.post(f"/cases/{case_id}/load-default-form", headers=headers).status_code == 404
    with SignedOut(client) as anonymous:
        assert anonymous.post(f"/cases/{case_id}/load-default-form").status_code == 401


# Preview


def test_the_preview_shows_every_onboarding_value_in_its_cell_as_a_draft(client: TestClient, tmp_path: Path) -> None:
    case_id, form_id, values = _prepared(client, tmp_path)
    assert {key: values[key] for key in ("full_name", "national_id", "email", "address_he")} == {
        key: _TYPED[key] for key in ("full_name", "national_id", "email", "address_he")
    }

    preview = client.get(f"/cases/{case_id}/documents/{form_id}/filled-preview")
    assert preview.status_code == 200, preview.text
    document = _assert_filled(preview.content, values, tmp_path)
    try:
        assert document.page_count == 2
        shown = " ".join(page.get_text() for page in document)
        assert "טיוטה" in shown or "הטויט" in shown
        assert document[1].get_image_info() == []
    finally:
        document.close()
    # The stored blank is never written to.
    assert client.get(f"/cases/{case_id}/documents/{form_id}/file").content == _blank()

    token = _token(client, case_id)
    signer = client.get("/portal/preview", headers=_auth(token))
    assert signer.status_code == 200, signer.text
    seen = _assert_filled(signer.content, values, tmp_path)
    try:
        assert seen.page_count == 2
        assert "DRAFT - NOT SIGNED" in " ".join(page.get_text() for page in seen)
    finally:
        seen.close()


# Signing


def test_the_new_hire_signs_form_101_through_the_link_and_the_seal_verifies(
    client: TestClient, tmp_path: Path
) -> None:
    case_id, form_id, values = _prepared(client, tmp_path)
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
    packet = client.get(f"/cases/{case_id}/signed-document").content
    assert hashlib.sha256(packet).hexdigest() == seal["file_sha256"]
    assert client.get("/portal/signed-document", headers=_auth(token)).content == packet

    document = _assert_filled(packet, values, tmp_path)
    try:
        # The two form pages, then the seal page.
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
        assert seal["signer_verification_id"] in document[2].get_text()
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

    events = [event["action"] for event in _timeline(client, case_id)]
    assert events.index("default_form_loaded") < events.index("fill_and_sign")

    # The export names the form after its process and carries the same bytes.
    bundle, manifest = _archive(client, case_id)
    assert "form_101_signed.pdf" in bundle.namelist()
    assert not any(name.startswith("bl_6101") for name in bundle.namelist())
    assert bundle.read("form_101_signed.pdf") == packet
    assert manifest["process_type"] == _KEY
    assert manifest["form_pdf"] == {
        "archive_path": "form_101_signed.pdf",
        "kind": "signed",
        "sha256": seal["file_sha256"],
    }
    # The blank it was signed on is kept beside the evidence.
    assert any(item["id"] == form_id and item["role"] == "form" for item in manifest["documents"])


def test_the_office_signs_at_the_desk_and_the_draft_export_is_named_form_101(
    client: TestClient, tmp_path: Path
) -> None:
    case_id, form_id, values = _prepared(client, tmp_path)
    bundle, manifest = _archive(client, case_id)
    assert manifest["form_pdf"]["archive_path"] == "form_101_draft.pdf"
    assert manifest["form_pdf"]["document_id"] == form_id
    draft = _assert_filled(bundle.read("form_101_draft.pdf"), values, tmp_path)
    draft.close()

    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert signed.status_code == 200, signed.text
    packet = client.get(f"/cases/{case_id}/signed-document").content
    document = _assert_filled(packet, values, tmp_path)
    try:
        assert document.page_count == 3
        assert document[1].get_image_info() != []
    finally:
        document.close()

    reopened = client.post(f"/cases/{case_id}/reopen")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["field_values"] == values
    assert reopened.json()["ready_to_sign"] is True
    assert [item["document_id"] for item in _forms(client, case_id)] == [form_id]


def test_an_onboarding_case_with_no_form_still_signs_the_generated_template(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client)
    body = _fill(client, case_id, tmp_path)
    assert _forms(client, case_id) == []
    assert body["ready_to_sign"] is True, body["signing_blockers"]
    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert signed.status_code == 200, signed.text
    document = pymupdf.open(stream=client.get(f"/cases/{case_id}/signed-document").content, filetype="pdf")
    try:
        # The one template page, then the seal page.
        assert document.page_count == 2
    finally:
        document.close()


def test_other_processes_keep_their_own_archive_names(client: TestClient) -> None:
    from app.domain.archive import form_names

    assert form_names("bl_6101") == ("bl_6101_signed.pdf", "bl_6101_draft.pdf")
    assert form_names("onboarding") == ("form_101_signed.pdf", "form_101_draft.pdf")
    assert form_names("employee_onboarding") == ("form_101_signed.pdf", "form_101_draft.pdf")
    assert form_names("real_estate") == ("real_estate_signed.pdf", "real_estate_draft.pdf")


# Catalog


def test_the_catalog_lists_onboarding_as_form_101_ready_to_load(client: TestClient) -> None:
    listed = client.get("/templates").json()
    assert [item["process_type"] for item in listed][:4] == [
        "bl_6101",
        "onboarding",
        "real_estate",
        "employee_onboarding",
    ]
    form = next(item for item in listed if item["process_type"] == _KEY)
    assert form["title_he"] == "טופס 101 – קליטת עובד חדש"
    assert form["form_source"] == "official_blank"
    assert form["default_template_available"] is True
    assert [item["id"] for item in form["required_drawers"] if item["required"]] == [
        "id_copy",
        "tax_form",
        "bank_confirmation",
    ]
    fields = {item["key"]: item for item in form["mapped_fields"]}
    assert list(fields) == _SLOTS
    assert (fields["national_id"]["target"]["page"], fields["national_id"]["target"]["mode"]) == (1, "digit_boxes")
    assert {(item["target"]["page"], item["target"]["mode"]) for key, item in fields.items() if key != "national_id"} == {
        (1, "text")
    }
    # The real estate process starts from its own blank too.
    deal = next(item for item in listed if item["process_type"] == "real_estate")
    assert deal["form_source"] == "official_blank"
