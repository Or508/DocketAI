"""BL/6101 is filled from documents onto an uploaded flat form, then signed there."""

import base64
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from app.catalog.processes import PROCESSES
from app.domain.text_layout import contains_hebrew, shape_for_pdf
from app.schemas.process import FieldSpec
from app.services.flat_form import read_flat_anchors, signature_box
from app.services.pdf_filler import _readback_matches

_FONT = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "Rubik-Regular.ttf"
_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAADIAAAAUCAIAAABAqPnNAAAALklEQVR4nO3OMQEAAAyDMP"
    "yb3jTw9SAKAnB7Fk9Xy6ll1DJqGbWMWkYto5ZRy3gIz6nxyF1oDwAAAABJRU5ErkJggg=="
)
_ID = "100000009"
_FIELDS = [
    FieldSpec.model_validate(item)
    for item in next(process for process in PROCESSES if process.key == "bl_6101").required_fields
]
_SLOTS = [
    ("national_id", "מספר זהות"),
    ("first_name", "שם פרטי"),
    ("last_name", "שם משפחה"),
    ("city", "יישוב"),
    ("street", "רחוב / תא דואר"),
    ("house_number", "מס' בית"),
    ("phone", "טלפון נייד"),
    ("bank_name", "שם הבנק"),
    ("bank_branch", "מס' סניף"),
    ("bank_account", "מספר החשבון"),
]
_SECTION_STARTS = {
    "national_id": "פרטי המבוטח",
    "city": "כתובת מגורים ופרטי התקשרות",
    "bank_name": "פרטי חשבון הבנק של המבוטח",
}
_VALUES = {
    "national_id": _ID,
    "first_name": "דנה",
    "last_name": "כהן",
    "city": "תל אביב",
    "street": "הרצל 15",
    "house_number": "10",
    "phone": "0501234567",
    "bank_name": "לאומי",
    "bank_branch": "800",
    "bank_account": "456789",
}
_DOCUMENT_SLOTS = {
    "national_id": "id_copy",
    "first_name": "id_copy",
    "last_name": "id_copy",
    "city": "proof_of_address",
    "street": "proof_of_address",
    "bank_name": "bank_confirmation",
    "bank_branch": "bank_confirmation",
    "bank_account": "bank_confirmation",
}
_LONG_STREET = "הרצל 15 תל אביב דירה שלוש קומה שתיים כניסה א"


class _Transcriber:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.calls = 0

    async def transcribe(self, images: list) -> str:
        self.calls += 1
        return self.transcript


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


def _label(page, right: float, baseline: float, text: str) -> None:
    shown = shape_for_pdf(text)
    width = pymupdf.Font(fontfile=str(_FONT)).text_length(shown, fontsize=8)
    page.insert_text((right - width, baseline), shown, fontname="rubik", fontsize=8)


def _bl_form(path: Path, *, bare: str | None = None, narrow: bool = False, copy_mark: str | None = None) -> Path:
    """One drawn cell per slot, plus a single signature rule. No widgets."""
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_font(fontname="rubik", fontfile=str(_FONT))
    top = 48.0
    for key, label in _SLOTS:
        if key in _SECTION_STARTS:
            _label(page, 540, top + 8, _SECTION_STARTS[key])
            top += 16
        if key == bare:
            _label(page, 540, top + 12, label)
            top += 36
            continue
        if narrow and key == "street":
            _label(page, 540, top + 12, label)
            page.draw_line((452, top + 14), (480, top + 14), width=0.7)
            top += 40
            continue
        page.draw_rect(pymupdf.Rect(280, top, 540, top + 40), width=0.7)
        _label(page, 536, top + 10, label)
        top += 48
    _label(page, 320, 680, "חתימת המבוטח")
    page.insert_text((246, 680), "×", fontsize=9)
    page.insert_text((60, 680), "_" * 32, fontsize=10)
    if copy_mark:
        page.insert_text((36, 36), copy_mark, fontsize=8)
    document.save(path)
    document.close()
    return path


def _pdf(path: Path, lines: list[str]) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_font(fontname="rubik", fontfile=str(_FONT))
    y = 72.0
    for line in lines:
        page.insert_textbox(pymupdf.Rect(72, y, 520, y + 24), line, fontname="rubik", fontsize=14)
        y += 32
    document.save(path)
    document.close()
    return path.read_bytes()


def _image_pdf(path: Path) -> bytes:
    image_path = path.with_suffix(".png")
    image = Image.new("RGB", (800, 240), "white")
    draw = ImageDraw.Draw(image)
    shown = shape_for_pdf("כתובת הנכס: הרצל 15, תל אביב")
    draw.text((24, 40), shown, fill="black", font=ImageFont.truetype(str(_FONT), 28))
    image.save(image_path)
    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(pymupdf.Rect(72, 72, 520, 280), filename=str(image_path))
    document.save(path)
    document.close()
    return path.read_bytes()


def _enable(database: Path, type_keys: set[str]) -> None:
    connection = sqlite3.connect(database)
    raw = connection.execute(
        "SELECT required_documents FROM process_definitions WHERE key = 'bl_6101'"
    ).fetchone()
    documents = json.loads(raw[0])
    for item in documents:
        if item.get("type_key") in type_keys and item.get("reading"):
            item["reading"]["enabled"] = True
    connection.execute(
        "UPDATE process_definitions SET required_documents = ? WHERE key = 'bl_6101'",
        (json.dumps(documents, ensure_ascii=False),),
    )
    connection.commit()
    connection.close()


def _open(client: TestClient) -> str:
    created = client.post(
        "/cases",
        json={"name": "BL 6101", "process_key": "bl_6101", "client_name": "דנה"},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _upload(client: TestClient, case_id: str, name: str, data: bytes) -> str:
    uploaded = client.post(
        f"/cases/{case_id}/upload",
        files=[("files", (name, data, "application/pdf"))],
    )
    assert uploaded.status_code == 200, uploaded.text
    unrecognized = client.get(f"/cases/{case_id}").json()["gap"]["unrecognized"]
    return next(item["document_id"] for item in unrecognized if item["filename"] == name)


def _classify(client: TestClient, case_id: str, document_id: str, document_type: str) -> dict:
    classified = client.post(
        f"/cases/{case_id}/classify-manual",
        json={"document_id": document_id, "document_type": document_type},
    )
    assert classified.status_code == 200, classified.text
    return classified.json()


def _mark(client: TestClient, case_id: str, document_id: str) -> None:
    marked = client.put(
        f"/cases/{case_id}/documents/{document_id}/role",
        json={"role": "form"},
    )
    assert marked.status_code == 200, marked.text


def _set(client: TestClient, case_id: str, key: str, value: str) -> dict:
    updated = client.post(f"/cases/{case_id}/fields", json={"key": key, "value": value})
    assert updated.status_code == 200, updated.text
    return updated.json()


def _sources(client: TestClient, case_id: str, tmp_path: Path) -> None:
    for name, document_type, line in (
        ("id-slip.pdf", "id_copy", "צילום תעודה"),
        ("arnona-bill.pdf", "proof_of_address", "חשבון ארנונה"),
        ("bank-letter.pdf", "bank_confirmation", "אישור בנק"),
    ):
        document_id = _upload(client, case_id, name, _pdf(tmp_path / name, [line]))
        _classify(client, case_id, document_id, document_type)


def _sign_body() -> dict:
    return {"signature_png_base64": _PNG_B64, "field_values": {}, "consent": True}


def _audit_value(database: Path, case_id: str) -> dict:
    connection = sqlite3.connect(database)
    rows = connection.execute("SELECT case_id, action, new_value FROM audit_logs").fetchall()
    connection.close()
    wanted = case_id.replace("-", "")
    for stored_case, action, raw in rows:
        if str(action) != "fill_and_sign":
            continue
        if str(stored_case).replace("-", "") == wanted and raw:
            return json.loads(raw)
    raise AssertionError("fill_and_sign audit row was not stored")


def _signed_objects(storage: Path) -> list[Path]:
    return [path for path in storage.rglob("*") if path.is_file() and "signed" in path.parts]


def _read_back(pdf: bytes, form_path: Path, values: dict[str, str]) -> None:
    anchors = {anchor["slot_key"]: anchor for anchor in read_flat_anchors(form_path, _FIELDS)}
    opened = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        for key, value in values.items():
            anchor = anchors[key]
            text = opened[anchor["page"]].get_text("text", clip=pymupdf.Rect(anchor["rect"]))
            assert _readback_matches(value, text, contains_hebrew(value)), (key, text)
    finally:
        opened.close()


def test_reading_is_on_for_this_process_only() -> None:
    switched = {
        process.key: {
            document["type_key"]: document["reading"]["enabled"]
            for document in process.required_documents
            if document.get("reading")
        }
        for process in PROCESSES
    }
    assert switched["bl_6101"] == {"id_copy": True, "proof_of_address": True, "bank_confirmation": True}
    others = [flag for key, flags in switched.items() if key != "bl_6101" for flag in flags.values()]
    assert others and not any(others)


def test_valid_fill_reads_every_value_back_and_reports_ok(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    form_path = _bl_form(tmp_path / "bl.pdf")
    document_id = _upload(client, case_id, "bl.pdf", form_path.read_bytes())
    _mark(client, case_id, document_id)
    for key, value in _VALUES.items():
        _set(client, case_id, key, value)

    preview = client.get(f"/cases/{case_id}/documents/{document_id}/filled-preview")
    assert preview.status_code == 200, preview.text
    assert preview.content.startswith(b"%PDF")
    _read_back(preview.content, form_path, _VALUES)

    report = client.get(f"/cases/{case_id}/documents/{document_id}/fill-report")
    assert report.status_code == 200, report.text
    rows = report.json()["fields"]
    assert {row["slot_key"] for row in rows} == set(_VALUES)
    assert {row["status"] for row in rows} == {"ok"}


def test_street_and_house_number_land_in_different_cells(client: TestClient, tmp_path: Path) -> None:
    process = next(item for item in PROCESSES if item.key == "bl_6101")
    rules = [
        rule
        for document in process.required_documents
        for rule in (document.get("reading") or {}).get("rules", [])
    ]
    # A house number is read only beside a printed label, never picked out of loose digits.
    assert all(rule["kind"] == "labeled" for rule in rules if rule["slot_key"] == "house_number")
    case_id = _open(client)
    form_path = _bl_form(tmp_path / "bl.pdf")
    document_id = _upload(client, case_id, "bl.pdf", form_path.read_bytes())
    _mark(client, case_id, document_id)
    _set(client, case_id, "street", "הרצל")
    _set(client, case_id, "house_number", "10")

    preview = client.get(f"/cases/{case_id}/documents/{document_id}/filled-preview")
    assert preview.status_code == 200, preview.text
    anchors = {anchor["slot_key"]: anchor for anchor in read_flat_anchors(form_path, _FIELDS)}
    street = pymupdf.Rect(anchors["street"]["rect"])
    house = pymupdf.Rect(anchors["house_number"]["rect"])
    assert not street.intersects(house)
    _read_back(preview.content, form_path, {"street": "הרצל", "house_number": "10"})


def test_documents_fill_only_the_slots_they_declare_and_keep_an_office_value(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client)
    _enable(tmp_path / "test.db", set(_DOCUMENT_SLOTS.values()))
    kept = _set(client, case_id, "street", "הרצל 10")
    assert kept["field_sources"]["street"]["source"] == "office"

    files = {
        "id.pdf": (
            "id_copy",
            [f"שם פרטי: {_VALUES['first_name']}", f"שם משפחה: {_VALUES['last_name']}", _ID],
        ),
        "arnona.pdf": (
            "proof_of_address",
            ["רחוב", "הרצל 15", "עיר", "תל אביב"],
        ),
        "bank.pdf": (
            "bank_confirmation",
            ["שם הבנק: לאומי", "מספר סניף", "800", "מספר חשבון", "456789"],
        ),
    }
    body = None
    for name, (document_type, lines) in files.items():
        document_id = _upload(client, case_id, name, _pdf(tmp_path / name, lines))
        body = _classify(client, case_id, document_id, document_type)
    assert body is not None
    values = body["field_values"]
    sources = body["field_sources"]
    for key in _DOCUMENT_SLOTS:
        if key == "street":
            continue
        assert values[key] == _VALUES[key]
        assert sources[key]["source"] == "document"
    assert values["street"] == "הרצל 10"
    assert sources["street"]["source"] == "office"
    assert "phone" not in values
    conflicts = [item for reading in body["readings"] for item in reading["conflicts"]]
    assert any(item["slot_key"] == "street" for item in conflicts)


def test_two_labeled_streets_are_ambiguous_and_stay_empty(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    _enable(tmp_path / "test.db", {"proof_of_address"})
    document_id = _upload(
        client,
        case_id,
        "arnona.pdf",
        _pdf(tmp_path / "arnona.pdf", ["רחוב", "הרצל 10", "רחוב", "ויצמן 5"]),
    )
    body = _classify(client, case_id, document_id, "proof_of_address")
    assert "street" not in body["field_values"]
    skips = [item for reading in body["readings"] for item in reading["skips"]]
    assert any(item["slot_key"] == "street" and item["reason"] == "ambiguous_match" for item in skips)


def test_a_noisy_street_line_never_keeps_the_account_column(client: TestClient, tmp_path: Path) -> None:
    noisy = "כתובת הנכס הרצל 15 תל אביב מספר חשבון לקוח 000111"
    case_id = _open(client)
    _enable(tmp_path / "test.db", {"proof_of_address"})
    document_id = _upload(client, case_id, "arnona.pdf", _pdf(tmp_path / "arnona.pdf", [noisy]))
    body = _classify(client, case_id, document_id, "proof_of_address")
    street = body["field_values"].get("street", "")
    assert street != noisy
    assert "000111" not in street
    assert "מספר חשבון" not in street


def test_office_correction_replaces_a_document_value_before_signature(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client)
    _enable(tmp_path / "test.db", {"proof_of_address"})
    source_id = _upload(
        client,
        case_id,
        "arnona.pdf",
        _pdf(tmp_path / "arnona.pdf", ["רחוב", "הרצל 15"]),
    )
    filled = _classify(client, case_id, source_id, "proof_of_address")
    assert filled["field_sources"]["street"]["source"] == "document"

    form_path = _bl_form(tmp_path / "bl.pdf")
    form_id = _upload(client, case_id, "bl.pdf", form_path.read_bytes())
    _mark(client, case_id, form_id)
    corrected = _set(client, case_id, "street", "ויצמן 5")
    assert corrected["field_values"]["street"] == "ויצמן 5"
    assert corrected["field_sources"]["street"]["source"] == "office"

    preview = client.get(f"/cases/{case_id}/documents/{form_id}/filled-preview")
    assert preview.status_code == 200, preview.text
    _read_back(preview.content, form_path, {"street": "ויצמן 5"})


def test_an_unknown_field_key_is_rejected(client: TestClient) -> None:
    case_id = _open(client)
    rejected = client.post(f"/cases/{case_id}/fields", json={"key": "contract_clause", "value": "x"})
    assert rejected.status_code == 400, rejected.text


def test_an_old_portal_digest_is_rejected_after_an_office_edit(client: TestClient, tmp_path: Path) -> None:
    case_id, form_id = _ready(client, tmp_path)
    token = _token(client, case_id)
    digest = client.get("/portal", headers=_auth(token)).json()["review_digest"]
    _set(client, case_id, "city", "חיפה")
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG_B64, "review_digest": digest, "consent": True},
    )
    assert signed.status_code == 409, signed.text


def test_a_label_with_no_drawn_target_has_no_anchor_and_stays_open(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client)
    form_path = _bl_form(tmp_path / "bl.pdf", bare="street")
    document_id = _upload(client, case_id, "bl.pdf", form_path.read_bytes())
    anchors = {anchor["slot_key"] for anchor in read_flat_anchors(form_path, _FIELDS)}
    assert "street" not in anchors
    _mark(client, case_id, document_id)
    report = client.get(f"/cases/{case_id}/documents/{document_id}/fill-report")
    assert report.status_code == 200, report.text
    assert all(row["slot_key"] != "street" for row in report.json()["fields"])
    intake = client.get(f"/cases/{case_id}/intake")
    assert intake.status_code == 200, intake.text
    assert any(slot["key"] == "street" for slot in intake.json()["open_slots"])


def test_an_image_only_page_with_an_empty_transcript_writes_nothing(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _open(client)
    _enable(tmp_path / "test.db", {"proof_of_address"})
    transcriber = _Transcriber("")
    client.app.state.container.pipeline._transcriber = transcriber
    document_id = _upload(client, case_id, "arnona-photo.pdf", _image_pdf(tmp_path / "arnona-photo.pdf"))
    assert transcriber.calls == 1
    connection = sqlite3.connect(tmp_path / "test.db")
    stored = connection.execute(
        "SELECT extracted_text FROM documents WHERE original_filename = ?",
        ("arnona-photo.pdf",),
    ).fetchone()
    connection.close()
    assert not (stored[0] or "").strip()
    body = _classify(client, case_id, document_id, "proof_of_address")
    assert "street" not in body["field_values"]
    assert "city" not in body["field_values"]
    skips = [item for reading in body["readings"] for item in reading["skips"]]
    assert any(item["reason"] == "no_text_layer" for item in skips)


def test_the_office_signs_the_uploaded_form(client: TestClient, tmp_path: Path) -> None:
    case_id, form_id = _ready(client, tmp_path)
    form_path = tmp_path / "form-0.pdf"
    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert signed.status_code == 200, signed.text
    audit = signed.json()["case"]["audit"]
    recorded = _audit_value(tmp_path / "test.db", case_id)
    assert recorded["form_document_id"] == form_id
    assert recorded["fields"]
    packet = client.get(f"/cases/{case_id}/signed-document")
    assert packet.status_code == 200, packet.text
    opened = pymupdf.open(stream=packet.content, filetype="pdf")
    try:
        assert opened.page_count == 2
        _page_values(opened[0], form_path, _VALUES)
        page_index, rect = signature_box(form_path, ["חתימת המבוטח"])
        assert page_index == 0
        box = pymupdf.Rect(rect)
        inside = [
            info
            for info in opened[0].get_image_info()
            if pymupdf.Rect(info["bbox"]).intersects(box)
        ]
        assert len(inside) == 1
    finally:
        opened.close()
    stored_form = next(path for path in _signed_objects(tmp_path / "storage") if path.name == "form.pdf")
    assert hashlib.sha256(stored_form.read_bytes()).hexdigest() == audit["content_sha256"]


def test_the_marked_form_needs_no_document_type_to_sign(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    _sources(client, case_id, tmp_path)
    form_path = _bl_form(tmp_path / "bl.pdf")
    form_id = _upload(client, case_id, "bl.pdf", form_path.read_bytes())
    waiting = client.get(f"/cases/{case_id}").json()
    assert [item["document_id"] for item in waiting["gap"]["unrecognized"]] == [form_id]
    _mark(client, case_id, form_id)
    for key, value in _VALUES.items():
        _set(client, case_id, key, "5" if key == "house_number" else value)
    workspace = client.get(f"/cases/{case_id}").json()
    assert workspace["gap"]["unrecognized"] == []
    assert workspace["ready_to_sign"] is True, workspace["signing_blockers"]
    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert signed.status_code == 200, signed.text
    assert _audit_value(tmp_path / "test.db", case_id)["form_document_id"] == form_id


def test_the_portal_preview_is_marked_draft_and_signs(client: TestClient, tmp_path: Path) -> None:
    case_id, _form_id = _ready(client, tmp_path)
    token = _token(client, case_id)
    preview = client.get("/portal/preview", headers=_auth(token))
    assert preview.status_code == 200, preview.text
    opened = pymupdf.open(stream=preview.content, filetype="pdf")
    try:
        text = "\n".join(page.get_text() for page in opened)
    finally:
        opened.close()
    assert "DRAFT - NOT SIGNED" in text
    digest = client.get("/portal", headers=_auth(token)).json()["review_digest"]
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG_B64, "review_digest": digest, "consent": True},
    )
    assert signed.status_code == 200, signed.text


def test_portal_sign_rejects_a_digest_from_before_an_office_edit(
    client: TestClient, tmp_path: Path
) -> None:
    case_id, _form_id = _ready(client, tmp_path)
    token = _token(client, case_id)
    digest = client.get("/portal", headers=_auth(token)).json()["review_digest"]
    _set(client, case_id, "phone", "0507654321")
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG_B64, "review_digest": digest, "consent": True},
    )
    assert signed.status_code == 409, signed.text


def test_signing_requires_exactly_one_marked_form(client: TestClient, tmp_path: Path) -> None:
    unmarked, _form_id = _ready(client, tmp_path, mark=False)
    before = _signed_objects(tmp_path / "storage")
    missing = client.post(f"/cases/{unmarked}/fill-and-sign", json=_sign_body())
    assert missing.status_code == 409, missing.text
    assert "Mark exactly one uploaded form" in missing.text
    assert _signed_objects(tmp_path / "storage") == before

    doubled, _ids = _ready(client, tmp_path, forms=2)
    refused = client.post(f"/cases/{doubled}/fill-and-sign", json=_sign_body())
    assert refused.status_code == 409, refused.text
    assert "Mark exactly one uploaded form" in refused.text
    assert _signed_objects(tmp_path / "storage") == before


def test_a_value_that_does_not_fit_is_refused_and_stores_nothing(
    client: TestClient, tmp_path: Path
) -> None:
    case_id, _form_id = _ready(client, tmp_path, narrow=True)
    before = _signed_objects(tmp_path / "storage")
    refused = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert refused.status_code == 422, refused.text
    assert "could not be written" in refused.text
    workspace = client.get(f"/cases/{case_id}")
    assert workspace.json()["case"]["status"] != "signed"
    assert _signed_objects(tmp_path / "storage") == before


def test_onboarding_still_signs_its_template(client: TestClient, tmp_path: Path) -> None:
    created = client.post(
        "/cases",
        json={"name": "Dana Cohen", "process_key": "onboarding", "client_name": "Dana"},
    )
    assert created.status_code == 201, created.text
    case_id = created.json()["id"]
    for name, document_type in (
        ("a-id.pdf", "id_copy"),
        ("b-tax.pdf", "tax_form"),
        ("c-bank.pdf", "bank_confirmation"),
    ):
        document_id = _upload(client, case_id, name, _pdf(tmp_path / name, [name]))
        _classify(client, case_id, document_id, document_type)
    answers = {
        "full_name": "Dana Cohen",
        "national_id": "123456782",
        "email": "dana@example.com",
        "phone": "0501234567",
        "address_he": "הרצל 1 תל אביב",
        "start_date": "04/11/2026",
    }
    for key, value in answers.items():
        _set(client, case_id, key, value)
    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert signed.status_code == 200, signed.text
    assert signed.json()["case"]["audit"]["is_signed"] is True
    assert "form_document_id" not in _audit_value(tmp_path / "test.db", case_id)
    packet = client.get(f"/cases/{case_id}/signed-document")
    assert packet.status_code == 200
    assert packet.content.startswith(b"%PDF")


def _ready(
    client: TestClient,
    tmp_path: Path,
    *,
    forms: int = 1,
    mark: bool = True,
    narrow: bool = False,
) -> tuple[str, str]:
    case_id = _open(client)
    _sources(client, case_id, tmp_path)
    form_id = ""
    for index in range(forms):
        path = tmp_path / f"form-{index}.pdf"
        _bl_form(path, narrow=narrow and index == 0, copy_mark=None if index == 0 else "SECOND")
        document_id = _upload(client, case_id, path.name, path.read_bytes())
        _classify(client, case_id, document_id, "id_copy")
        if mark:
            _mark(client, case_id, document_id)
        form_id = document_id
    for key, value in _VALUES.items():
        _set(client, case_id, key, _LONG_STREET if narrow and key == "street" else value)
    return case_id, form_id


def _page_values(page, form_path: Path, values: dict[str, str]) -> None:
    anchors = {anchor["slot_key"]: anchor for anchor in read_flat_anchors(form_path, _FIELDS)}
    for key, value in values.items():
        text = page.get_text("text", clip=pymupdf.Rect(anchors[key]["rect"]))
        assert _readback_matches(value, text, contains_hebrew(value)), (key, text)


def _token(client: TestClient, case_id: str) -> str:
    created = client.post(f"/cases/{case_id}/signing-links")
    assert created.status_code == 201, created.text
    return created.json()["url"].rstrip("/").rsplit("/", 1)[-1]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
