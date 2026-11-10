import base64
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("reportlab")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

import pymupdf
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from sqlalchemy import select

from app.catalog.processes import PROCESSES
from app.db.session import session_scope
from app.domain.enums import AuditAction
from app.domain.form_anchors import SYNONYM_INDEX, bind_widget, normalize
from app.models.audit_log import AuditLog
from app.schemas.process import FieldSpec
from app.services.pdf_filler import read_form_widgets

_PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAADIAAAAUCAIAAABAqPnNAAAALklEQVR4nO3OMQEAAAyDMPyb3jTw9SAKAnB7Fk9Xy6ll1DJqGbWMWkYto5ZRy3gIz6nxyF1oDwAAAABJRU5ErkJggg=="
    )
).decode()
_ONBOARDING = [
    FieldSpec.model_validate(item)
    for item in next(process for process in PROCESSES if process.key == "onboarding").required_fields
]


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


def _form(path: Path, text_widgets: list[tuple[str, str]], *, checkbox: str | None = None) -> bytes:
    """An AcroForm with one text widget per (name, value); an empty value is an empty field."""
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 60), "Client form")
    top = 90
    for name, value in text_widgets:
        widget = pymupdf.Widget()
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.field_name = name
        widget.field_value = value
        widget.rect = pymupdf.Rect(200, top, 450, top + 20)
        page.add_widget(widget)
        top += 30
    if checkbox:
        box = pymupdf.Widget()
        box.field_type = pymupdf.PDF_WIDGET_TYPE_CHECKBOX
        box.field_name = checkbox
        box.rect = pymupdf.Rect(200, top, 214, top + 14)
        page.add_widget(box)
    document.save(path)
    document.close()
    return path.read_bytes()


def _plain_pdf(path: Path, text: str) -> bytes:
    form = canvas.Canvas(str(path))
    form.drawString(72, 720, text)
    form.save()
    return path.read_bytes()


def _case(client: TestClient) -> str:
    created = client.post("/cases", json={"name": "Anchors", "process_key": "onboarding", "client_name": "Dana"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def _prefill_audits() -> list[AuditLog]:
    async with session_scope() as session:
        rows = await session.scalars(select(AuditLog).where(AuditLog.action == AuditAction.FIELD_PREFILLED))
        return list(rows)


# Binding


def test_binding_is_exact_then_closed_synonyms_only() -> None:
    assert bind_widget("full_name", _ONBOARDING).match == "exact"
    synonym = bind_widget("טלפון נייד", _ONBOARDING)
    assert synonym is not None and (synonym.key, synonym.match) == ("phone", "synonym")
    hebrew_id = bind_widget('ת"ז', _ONBOARDING)
    assert hebrew_id is not None and hebrew_id.key == "national_id"
    assert bind_widget("Full_Name", _ONBOARDING).key == "full_name"
    # A synonym whose slot this process does not have stays unbound.
    assert "buyer" in SYNONYM_INDEX
    assert bind_widget("buyer", _ONBOARDING) is None
    # Free labels never bind, and nothing new is invented.
    assert bind_widget("favourite colour", _ONBOARDING) is None
    assert bind_widget("Signature of applicant", _ONBOARDING) is None


def test_every_synonym_points_to_one_existing_slot_key() -> None:
    known = {
        field["key"] for process in PROCESSES for field in process.required_fields
    }
    assert set(SYNONYM_INDEX.values()) <= known
    assert normalize(" Full-Name ") == normalize("full name")


def test_widget_reader_reports_empty_text_fields_and_skips_checkboxes(tmp_path: Path) -> None:
    path = tmp_path / "form.pdf"
    _form(path, [("full_name", ""), ("טלפון", "050-123-4567")], checkbox="agree")
    readings = {reading.field_name: reading for reading in read_form_widgets(path)}
    assert set(readings) == {"full_name", "טלפון"}
    assert readings["full_name"].empty is True
    assert readings["טלפון"].empty is False
    assert readings["טלפון"].value == "050-123-4567"
    assert readings["full_name"].page_index == 0
    x0, y0, x1, y1 = readings["full_name"].rect
    assert x1 > x0 and y1 > y0


# Upload flow


def test_uploaded_form_anchors_prefill_and_unbound_widgets(client: TestClient, tmp_path: Path) -> None:
    case_id = _case(client)
    office = client.post(f"/cases/{case_id}/fields", json={"key": "email", "value": "dana@example.com"})
    assert office.status_code == 200, office.text

    form = _form(
        tmp_path / "client-form.pdf",
        [
            ("full_name", ""),  # empty, exact match: an anchor on an open slot
            ("טלפון", "050-123-4567"),  # filled, synonym match: prefills the empty phone slot
            ('דוא"ל', "old@example.com"),  # filled, but the office already set a different email
            ("ת.ז", "123"),  # filled, but the validator rejects it
            ("favourite_colour", ""),  # no match: stays unbound
        ],
        checkbox="agree",
    )
    uploaded = client.post(
        f"/cases/{case_id}/upload",
        files=[("files", ("client-form.pdf", form, "application/pdf"))],
    )
    assert uploaded.status_code == 200, uploaded.text
    workspace = client.get(f"/cases/{case_id}").json()
    document_id = next(item["document_id"] for item in workspace["gap"]["unrecognized"])

    values = workspace["field_values"]
    sources = workspace["field_sources"]
    assert values["phone"]
    assert sources["phone"] == {"source": "document", "document_id": document_id}
    # The filled widget did not replace the office's value.
    assert values["email"] == "dana@example.com"
    assert sources["email"] == {"source": "office", "document_id": None}
    # An invalid widget value is not used.
    assert "national_id" not in values

    slots = {slot["key"]: slot for slot in workspace["open_slots"]}
    assert set(slots) == {"full_name", "national_id", "address_he", "start_date"}
    assert [anchor["field_name"] for anchor in slots["full_name"]["anchors"]] == ["full_name"]
    anchor = slots["full_name"]["anchors"][0]
    assert anchor["document_id"] == document_id and anchor["match"] == "exact" and anchor["page"] == 0
    assert len(anchor["rect"]) == 4
    # Slots without a matching empty widget stay ordinary questions.
    assert slots["address_he"]["anchors"] == []
    assert slots["start_date"]["anchors"] == []
    assert {item["key"] for item in workspace["missing_fields"]} == set(slots)

    unbound = workspace["unbound_anchors"]
    assert [(item["field_name"], item["empty"]) for item in unbound] == [("favourite_colour", True)]
    assert all(item["field_name"] != "agree" for item in unbound)

    audits = client.portal.call(_prefill_audits)
    assert [audit.new_value for audit in audits] == [{"fields": ["phone"]}]
    assert "050" not in str(audits[0].new_value)


def test_widgets_that_disagree_do_not_prefill(client: TestClient, tmp_path: Path) -> None:
    case_id = _case(client)
    form = _form(tmp_path / "twice.pdf", [("full_name", "Dana Cohen"), ("שם מלא", "Noa Levi")])
    uploaded = client.post(f"/cases/{case_id}/upload", files=[("files", ("twice.pdf", form, "application/pdf"))])
    assert uploaded.status_code == 200, uploaded.text
    workspace = client.get(f"/cases/{case_id}").json()
    assert "full_name" not in workspace["field_values"]
    assert client.portal.call(_prefill_audits) == []


def test_a_later_document_does_not_replace_a_prefilled_value(client: TestClient, tmp_path: Path) -> None:
    case_id = _case(client)
    first = _form(tmp_path / "first.pdf", [("full_name", "Dana Cohen")])
    second = _form(tmp_path / "second.pdf", [("full_name", "Noa Levi")])
    for name, data in (("first.pdf", first), ("second.pdf", second)):
        uploaded = client.post(f"/cases/{case_id}/upload", files=[("files", (name, data, "application/pdf"))])
        assert uploaded.status_code == 200, uploaded.text
    workspace = client.get(f"/cases/{case_id}").json()
    assert workspace["field_values"]["full_name"] == "Dana Cohen"
    first_id = next(item["document_id"] for item in workspace["gap"]["unrecognized"] if item["filename"] == "first.pdf")
    assert workspace["field_sources"]["full_name"] == {"source": "document", "document_id": first_id}


def test_client_answer_uses_the_existing_fill_path_with_rtl(client: TestClient, tmp_path: Path) -> None:
    case_id = _case(client)
    names = {"a-id.pdf": "identity card", "b-tax.pdf": "tax form 101", "c-bank.pdf": "bank confirmation"}
    files = [("files", (name, _plain_pdf(tmp_path / name, text), "application/pdf")) for name, text in names.items()]
    assert client.post(f"/cases/{case_id}/upload", files=files).status_code == 200
    found = {item["filename"]: item["document_id"] for item in client.get(f"/cases/{case_id}").json()["gap"]["unrecognized"]}
    for filename, document_type in {"a-id.pdf": "id_copy", "b-tax.pdf": "tax_form", "c-bank.pdf": "bank_confirmation"}.items():
        classified = client.post(
            f"/cases/{case_id}/classify-manual",
            json={"document_id": found[filename], "document_type": document_type},
        )
        assert classified.status_code == 200, classified.text
    for key, value in {
        "full_name": "Dana Cohen",
        "national_id": "123456782",
        "email": "dana@example.com",
        "phone": "0501234567",
        "start_date": "04/11/2026",
    }.items():
        assert client.post(f"/cases/{case_id}/fields", json={"key": key, "value": value}).status_code == 200

    link = client.post(f"/cases/{case_id}/signing-links").json()
    token = link["url"].rstrip("/").rsplit("/", 1)[-1]
    headers = {"Authorization": f"Bearer {token}"}
    answered = client.post("/portal/fields", headers=headers, json={"key": "address_he", "value": "הרצל 1 תל אביב"})
    assert answered.status_code == 200, answered.text
    view = answered.json()
    signed = client.post(
        "/portal/sign",
        headers=headers,
        json={"signature_png_base64": _PNG, "review_digest": view["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text

    workspace = client.get(f"/cases/{case_id}").json()
    assert workspace["field_sources"]["address_he"] == {"source": "client", "document_id": None}
    assert workspace["field_sources"]["full_name"] == {"source": "office", "document_id": None}
    pdf = pymupdf.open(stream=client.get(f"/cases/{case_id}/signed-document").content)
    try:
        text = "\n".join(page.get_text() for page in pdf)
    finally:
        pdf.close()
    assert "Dana Cohen" in text
    assert "הרצל" in text or "לצרה" in text
