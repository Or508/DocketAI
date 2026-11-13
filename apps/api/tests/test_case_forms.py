import base64
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.catalog.processes import PROCESSES
from app.db.session import session_scope
from app.domain.enums import AuditAction, CaseStatus
from app.domain.provenance import public_why
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.schemas.gap import WhyItem
from app.schemas.process import FieldSpec
from app.services.pdf_filler import PdfFillerService

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAADIAAAAUCAIAAABAqPnNAAAALklEQVR4nO3OMQEAAAyDMPyb3jTw9SAKAnB7Fk9Xy6ll1DJqGbWMWkYto5ZRy3gIz6nxyF1oDwAAAABJRU5ErkJggg=="
)
_ADDRESS = "רחוב הרצל 12, דירה 3"
_DRAFT = "טיוטה – לא חתום"
_PROMPTS = (
    "הנה מה שזיהינו שחסר בתיק – האם להוסיף מסמכים או פרטים נוספים שהבוט יבקש מהלקוח?",
    "Here is what we found missing in the case – should we add documents or further details for the bot to ask the client?",
)


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


def _acroform(path: Path, widgets: list[dict]) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    for item in widgets:
        widget = pymupdf.Widget()
        widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        widget.field_name = item["name"]
        widget.field_value = item.get("value", "")
        widget.rect = pymupdf.Rect(*item["rect"])
        flags = 0
        if item.get("comb"):
            flags |= pymupdf.PDF_TX_FIELD_IS_COMB
        if item.get("multiline"):
            flags |= pymupdf.PDF_TX_FIELD_IS_MULTILINE
        if flags:
            widget.field_flags = flags
        if item.get("maxlen"):
            widget.text_maxlen = item["maxlen"]
        page.add_widget(widget)
    document.save(path)
    data = path.read_bytes()
    document.close()
    return data


def _plain_pdf(path: Path) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "A note, not a form")
    document.save(path)
    data = path.read_bytes()
    document.close()
    return data


def _clip(data: bytes, rect: tuple[float, float, float, float]) -> str:
    document = pymupdf.open(stream=data, filetype="pdf")
    try:
        return document[0].get_text("text", clip=pymupdf.Rect(*rect))
    finally:
        document.close()


def _page_text(data: bytes) -> str:
    document = pymupdf.open(stream=data, filetype="pdf")
    try:
        return "\n".join(page.get_text("text") for page in document)
    finally:
        document.close()


def _letters(text: str) -> list[str]:
    return sorted(character for character in text if "\u0590" <= character <= "\u05FF")


def _digits(text: str) -> str:
    return "".join(character for character in text if character.isdigit())


def _fill(path: Path, values: dict[str, str], rtl: set[str] | None = None):
    return PdfFillerService(None).fill_case_form(source_path=path, values=values, rtl_names=rtl or set())


def _case(client: TestClient, name: str = "Secret Case Name") -> str:
    created = client.post("/cases", json={"name": name, "process_key": "onboarding", "client_name": "Dana"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _upload(client: TestClient, case_id: str, name: str, data: bytes, mime: str) -> str:
    uploaded = client.post(f"/cases/{case_id}/upload", files=[("files", (name, data, mime))])
    assert uploaded.status_code == 200, uploaded.text
    workspace = client.get(f"/cases/{case_id}").json()
    for bucket in ("unrecognized", "identified", "in_progress"):
        for item in workspace["gap"][bucket]:
            if item["filename"] == name:
                return item["document_id"]
    raise AssertionError(workspace["gap"])


def _string_wider_than(width: float, fontsize: float) -> str:
    text = "M"
    while pymupdf.get_text_length(text, fontname="helv", fontsize=fontsize) <= width:
        text += "M"
    return text


# Filling


def test_fill_writes_only_empty_widgets_and_leaves_the_original(tmp_path: Path) -> None:
    path = tmp_path / "form.pdf"
    empty_rect = (72, 80, 360, 102)
    filled_rect = (72, 120, 360, 142)
    other_rect = (72, 160, 360, 182)
    original = _acroform(
        path,
        [
            {"name": "full_name", "value": "", "rect": empty_rect},
            {"name": "email", "value": "Already There", "rect": filled_rect},
            {"name": "note", "value": "Leave Me", "rect": other_rect},
        ],
    )
    filled = _fill(path, {"full_name": "Dana Cohen", "email": "Should Not Replace"})
    assert path.read_bytes() == original
    by_name = {item.field_name: item for item in filled.fields}
    assert by_name["full_name"].status == "ok"
    assert by_name["full_name"].font_size == 11
    assert by_name["email"].status == "skipped_prefilled"
    assert by_name["email"].font_size is None
    assert "note" not in by_name
    assert "Dana Cohen" in _clip(filled.pdf_bytes, empty_rect)
    assert "Already There" in _clip(filled.pdf_bytes, filled_rect)
    assert "Should Not Replace" not in _clip(filled.pdf_bytes, filled_rect)
    assert "Leave Me" in _clip(filled.pdf_bytes, other_rect)


def test_hebrew_readback_keeps_letters_and_digit_sequence(tmp_path: Path) -> None:
    path = tmp_path / "rtl.pdf"
    rect = (72, 80, 520, 112)
    _acroform(path, [{"name": "address_he", "value": "", "rect": rect}])
    filled = _fill(path, {"address_he": _ADDRESS}, {"address_he"})
    field = filled.fields[0]
    clip = _clip(filled.pdf_bytes, rect)
    assert field.status == "ok", clip
    assert _letters(clip) in (_letters(_ADDRESS), sorted(_letters(_ADDRESS) + _letters(_ADDRESS)))
    assert _digits(_ADDRESS) == "123"
    assert _digits(clip) in {"123", "312", "123312", "312123"}


def test_font_shrinks_until_the_text_fits_and_maxlen_blocks_a_write(tmp_path: Path) -> None:
    path = tmp_path / "fit.pdf"
    narrow = (72, 80, 230, 102)
    limited = (72, 120, 400, 142)
    usable = (narrow[2] - narrow[0]) - 4
    shrinking = _string_wider_than(usable, 11)
    assert pymupdf.get_text_length(shrinking, fontname="helv", fontsize=7) <= usable
    _acroform(
        path,
        [
            {"name": "narrow", "value": "", "rect": narrow},
            {"name": "limited", "value": "", "rect": limited, "maxlen": 4},
        ],
    )
    filled = _fill(path, {"narrow": shrinking, "limited": "HELLO"})
    by_name = {item.field_name: item for item in filled.fields}
    assert by_name["narrow"].status == "ok"
    assert by_name["narrow"].font_size is not None and by_name["narrow"].font_size < 11
    assert shrinking in _clip(filled.pdf_bytes, narrow)
    assert by_name["limited"].status == "overflow"
    assert by_name["limited"].font_size is None
    assert "HELLO" not in _clip(filled.pdf_bytes, limited)

    overflow_path = tmp_path / "overflow.pdf"
    wide = (72, 80, 190, 102)
    too_long = _string_wider_than((wide[2] - wide[0]) - 4, 7)
    _acroform(overflow_path, [{"name": "wide", "value": "", "rect": wide}])
    overflowed = _fill(overflow_path, {"wide": too_long})
    assert overflowed.fields[0].status == "overflow"
    assert overflowed.fields[0].font_size is None
    assert too_long not in _page_text(overflowed.pdf_bytes)


def test_comb_widget_is_not_written(tmp_path: Path) -> None:
    path = tmp_path / "comb.pdf"
    rect = (72, 80, 360, 102)
    _acroform(path, [{"name": "code", "value": "", "rect": rect, "comb": True, "maxlen": 6}])
    filled = _fill(path, {"code": "ABC123"})
    assert filled.fields[0].status == "comb_unsupported"
    assert filled.fields[0].font_size is None
    assert "ABC123" not in _page_text(filled.pdf_bytes)


def test_the_same_inputs_produce_the_same_bytes(tmp_path: Path) -> None:
    path = tmp_path / "twice.pdf"
    _acroform(
        path,
        [
            {"name": "full_name", "value": "", "rect": (72, 80, 360, 102)},
            {"name": "address_he", "value": "", "rect": (72, 120, 520, 152)},
        ],
    )
    values = {"full_name": "Dana Cohen", "address_he": _ADDRESS}
    rtl = {"address_he"}
    first = _fill(path, values, rtl)
    second = _fill(path, values, rtl)
    assert first.pdf_bytes == second.pdf_bytes


@pytest.mark.parametrize(
    "source_id",
    [
        "[(abcdefghijklmnop)(abcdefghijklmnop)]",
        r"[(ab\)cd\\ef(gh)ijklmn)<00112233445566778899AABBCCDDEEFF>]",
        "[<00112233445566778899AABBCCDDEEFF><00112233445566778899AABBCCDDEEFF>]",
    ],
)
def test_the_same_bytes_whatever_form_the_source_id_takes(tmp_path: Path, source_id: str) -> None:
    """A source id made of printable bytes is written as a literal string, not as hex."""
    plain = tmp_path / "plain.pdf"
    _acroform(plain, [{"name": "full_name", "value": "", "rect": (72, 80, 360, 102)}])
    path = tmp_path / "literal.pdf"
    document = pymupdf.open(plain)
    document.xref_set_key(-1, "ID", source_id)
    document.save(path, no_new_id=True)
    document.close()
    first = _fill(path, {"full_name": "Dana Cohen"})
    second = _fill(path, {"full_name": "Dana Cohen"})
    assert first.pdf_bytes == second.pdf_bytes
    reopened = pymupdf.open(stream=first.pdf_bytes, filetype="pdf")
    assert reopened.page_count == 1
    reopened.close()


def test_multiline_text_fits_the_height_or_overflows(tmp_path: Path) -> None:
    path = tmp_path / "lines.pdf"
    tall = (72, 80, 200, 160)
    short = (72, 180, 200, 200)
    _acroform(
        path,
        [
            {"name": "notes", "value": "", "rect": tall, "multiline": True},
            {"name": "cramped", "value": "", "rect": short, "multiline": True},
        ],
    )
    value = "alpha beta gamma delta epsilon zeta eta theta"
    cramped_value = "one\ntwo\nthree\nfour"
    filled = _fill(path, {"notes": value, "cramped": cramped_value})
    by_name = {item.field_name: item for item in filled.fields}
    assert by_name["notes"].status == "ok"
    assert value.split()[0] in _clip(filled.pdf_bytes, tall)
    assert by_name["cramped"].status == "overflow"
    assert by_name["cramped"].font_size is None
    assert "four" not in _clip(filled.pdf_bytes, short)


# Role, preview, report, provenance, intake


def _office_form(client: TestClient, tmp_path: Path) -> tuple[str, str]:
    case_id = _case(client)
    form = _acroform(
        tmp_path / "office-secret-form.pdf",
        [
            {"name": "full_name", "value": "", "rect": (72, 80, 400, 102)},
            {"name": "phone", "value": "", "rect": (72, 120, 400, 142)},
            {"name": "email", "value": "dana@example.com", "rect": (72, 160, 400, 182)},
            {"name": "favourite_colour", "value": "", "rect": (72, 200, 400, 222)},
        ],
    )
    document_id = _upload(client, case_id, "office-secret-form.pdf", form, "application/pdf")
    return case_id, document_id


def test_role_rejects_a_non_form_and_a_signed_case_and_records_the_audit(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _case(client)
    png_id = _upload(client, case_id, "photo.png", _PNG, "image/png")
    plain_id = _upload(client, case_id, "notes.pdf", _plain_pdf(tmp_path / "notes.pdf"), "application/pdf")
    refused_png = client.put(f"/cases/{case_id}/documents/{png_id}/role", json={"role": "form"})
    refused_plain = client.put(f"/cases/{case_id}/documents/{plain_id}/role", json={"role": "form"})
    assert refused_png.status_code == 409, refused_png.text
    assert refused_plain.status_code == 409, refused_plain.text

    form = _acroform(
        tmp_path / "real-form.pdf",
        [{"name": "full_name", "value": "", "rect": (72, 80, 400, 102)}],
    )
    document_id = _upload(client, case_id, "real-form.pdf", form, "application/pdf")
    marked = client.put(
        f"/cases/{case_id}/documents/{document_id}/role",
        json={"role": "form", "display_title": "שאלון קליטה"},
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()["role"] == "form"
    assert marked.json()["display_title"] == "שאלון קליטה"

    async def audits() -> list[AuditLog]:
        async with session_scope() as session:
            rows = await session.scalars(
                select(AuditLog).where(AuditLog.action == AuditAction.DOCUMENT_ROLE_CHANGED)
            )
            return list(rows)

    recorded = client.portal.call(audits)
    assert len(recorded) == 1
    assert recorded[0].new_value == {"role": "form", "display_title": "שאלון קליטה"}
    assert recorded[0].document_id == UUID(document_id)

    async def sign() -> None:
        async with session_scope() as session:
            case = await session.get(Case, UUID(case_id))
            assert case is not None
            case.status = CaseStatus.SIGNED
            await session.commit()

    client.portal.call(sign)
    signed = client.put(f"/cases/{case_id}/documents/{document_id}/role", json={"role": "evidence"})
    assert signed.status_code == 409, signed.text
    assert len(client.portal.call(audits)) == 1


def test_another_organization_gets_404_on_every_new_route(client: TestClient, tmp_path: Path) -> None:
    from tests.support import authenticate

    case_id, document_id = _office_form(client, tmp_path)
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    routes = [
        ("PUT", f"/cases/{case_id}/documents/{document_id}/role", {"role": "form"}),
        ("GET", f"/cases/{case_id}/documents/{document_id}/filled-preview", None),
        ("GET", f"/cases/{case_id}/documents/{document_id}/fill-report", None),
        ("GET", f"/cases/{case_id}/intake", None),
    ]
    for method, path, payload in routes:
        response = client.request(method, path, json=payload, headers=headers)
        assert response.status_code == 404, f"{method} {path} -> {response.status_code} {response.text}"


def test_preview_is_watermarked_and_the_report_names_each_source(client: TestClient, tmp_path: Path) -> None:
    case_id, document_id = _office_form(client, tmp_path)
    early = client.get(f"/cases/{case_id}/documents/{document_id}/filled-preview")
    assert early.status_code == 409, early.text
    marked = client.put(f"/cases/{case_id}/documents/{document_id}/role", json={"role": "form"})
    assert marked.status_code == 200, marked.text
    named = client.post(f"/cases/{case_id}/fields", json={"key": "full_name", "value": "Dana Cohen"})
    assert named.status_code == 200, named.text

    original = client.get(f"/cases/{case_id}/documents/{document_id}/file")
    assert original.status_code == 200, original.text
    preview = client.get(f"/cases/{case_id}/documents/{document_id}/filled-preview")
    assert preview.status_code == 200, preview.text
    assert preview.headers["content-disposition"].startswith("inline")
    assert preview.headers["cache-control"] == "no-store"
    assert preview.content.startswith(b"%PDF")
    assert _DRAFT in _page_text(preview.content)
    again = client.get(f"/cases/{case_id}/documents/{document_id}/file")
    assert again.content == original.content

    report = client.get(f"/cases/{case_id}/documents/{document_id}/fill-report")
    assert report.status_code == 200, report.text
    fields = {item["field_name"]: item for item in report.json()["fields"]}
    assert set(fields) == {"full_name", "phone", "email"}
    assert fields["full_name"]["status"] == "ok"
    assert fields["full_name"]["source"] == "office"
    assert fields["full_name"]["slot_key"] == "full_name"
    assert fields["phone"]["status"] == "awaiting_value"
    assert fields["phone"]["source"] is None
    assert fields["email"]["status"] == "skipped_prefilled"
    assert fields["email"]["source"] == "document"


def test_provenance_is_bilingual_and_public_why_hides_office_identifiers(
    client: TestClient, tmp_path: Path
) -> None:
    case_id, document_id = _office_form(client, tmp_path)
    marked = client.put(f"/cases/{case_id}/documents/{document_id}/role", json={"role": "form"})
    assert marked.status_code == 200, marked.text
    workspace = client.get(f"/cases/{case_id}").json()
    phone = next(slot for slot in workspace["open_slots"] if slot["key"] == "phone")
    kinds = {item["kind"] for item in phone["why"]}
    assert kinds == {"template", "form"}
    template = next(item for item in phone["why"] if item["kind"] == "template")
    form_item = next(item for item in phone["why"] if item["kind"] == "form")
    assert template["text_he"] == (
        "הפרט נדרש כדי למלא את פרטי קשר בטופס קליטת עובד. מספר הטלפון משמש ליצירת קשר."
    )
    assert template["text_en"] == (
        "This detail is required to fill the contact details in the employee onboarding form. "
        "The phone number is used for contact."
    )
    assert form_item["text_he"] == "הפרט נדרש כדי למלא עבורך שדה ב«טופס המשרד» (עמוד 1)."
    assert form_item["text_en"] == (
        "This detail is required to fill a field for you in «the office form» (page 1)."
    )
    assert form_item["document_id"] == document_id
    public = public_why([WhyItem.model_validate(item) for item in phone["why"]])
    dumped = " ".join(item.model_dump_json() for item in public)
    assert "office-secret-form.pdf" not in dumped
    assert document_id not in dumped
    assert "Secret Case Name" not in dumped
    assert all(item.document_id is None and item.page is None for item in public)
    assert "טופס המשרד" in dumped

    titled = client.put(
        f"/cases/{case_id}/documents/{document_id}/role",
        json={"role": "form", "display_title": "שאלון קליטה"},
    )
    assert titled.status_code == 200, titled.text
    refreshed = client.get(f"/cases/{case_id}").json()
    phone = next(slot for slot in refreshed["open_slots"] if slot["key"] == "phone")
    form_item = next(item for item in phone["why"] if item["kind"] == "form")
    assert "שאלון קליטה" in form_item["text_he"]
    assert "שאלון קליטה" in form_item["text_en"]
    assert "office-secret-form.pdf" not in form_item["text_he"]
    assert "טופס המשרד" not in form_item["text_he"]


def test_intake_summary_counts_widgets_and_repeats_the_gap(client: TestClient, tmp_path: Path) -> None:
    case_id, document_id = _office_form(client, tmp_path)
    marked = client.put(
        f"/cases/{case_id}/documents/{document_id}/role",
        json={"role": "form", "display_title": "שאלון קליטה"},
    )
    assert marked.status_code == 200, marked.text
    summary = client.get(f"/cases/{case_id}/intake")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert len(body["forms"]) == 1
    form = body["forms"][0]
    assert form["document_id"] == document_id
    assert form["filename"] == "office-secret-form.pdf"
    assert form["role"] == "form"
    assert form["display_title"] == "שאלון קליטה"
    assert form["widgets_total"] == 4
    assert form["bound"] == 3
    assert form["bound_empty"] == 2
    assert form["unbound"] == 1
    gap = client.get(f"/cases/{case_id}/status").json()
    assert body["missing_documents"] == gap["missing"]
    assert body["prompt_he"] == _PROMPTS[0]
    assert body["prompt_en"] == _PROMPTS[1]
    phone = next(slot for slot in body["open_slots"] if slot["key"] == "phone")
    assert {item["kind"] for item in phone["why"]} == {"template", "form"}
    assert any(item["text_en"] and item["text_he"] for item in phone["why"])


def test_onboarding_and_real_estate_fields_carry_provenance() -> None:
    for process in PROCESSES:
        if process.key not in {"onboarding", "real_estate"}:
            continue
        for raw in process.required_fields:
            spec = FieldSpec.model_validate(raw)
            assert spec.provenance is not None
            parts = (
                spec.provenance.form_he,
                spec.provenance.section_he,
                spec.provenance.purpose_he,
                spec.provenance.form_en,
                spec.provenance.section_en,
                spec.provenance.purpose_en,
            )
            assert all(part and len(part) <= 200 for part in parts)


def _alembic(database: Path, *args: str) -> str:
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database.as_posix()}"}
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=root,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


def _document_columns(database: Path) -> dict[str, tuple]:
    connection = sqlite3.connect(database)
    rows = connection.execute("PRAGMA table_info(documents)").fetchall()
    connection.close()
    return {row[1]: row for row in rows}


def test_case_form_migration_goes_up_down_and_up(tmp_path: Path) -> None:
    database = tmp_path / "forms.db"
    _alembic(database, "upgrade", "head")
    columns = _document_columns(database)
    assert columns["role"][3] == 1
    assert "evidence" in str(columns["role"][4])
    assert columns["display_title"][3] == 0
    assert "reading_report" in columns
    current = _alembic(database, "current")
    assert "20261111_0009" in current

    _alembic(database, "downgrade", "20261110_0007")
    downgraded = _document_columns(database)
    assert "role" not in downgraded
    assert "display_title" not in downgraded

    _alembic(database, "upgrade", "head")
    restored = _document_columns(database)
    assert "role" in restored and "display_title" in restored and "reading_report" in restored
    assert "20261111_0009" in _alembic(database, "current")
