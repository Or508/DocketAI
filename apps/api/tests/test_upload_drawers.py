"""A file lands in the drawer the office picked, whatever its format or its text."""

import asyncio
import io
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

import pymupdf
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.catalog.processes import PROCESSES
from app.domain.slot_reading import read_document
from app.schemas.process import DocumentTypeSpec, FieldSpec
from app.services.uploads import detect_mime

_FONT = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "Rubik-Regular.ttf"
_BL = next(process for process in PROCESSES if process.key == "bl_6101")
_FIELDS = [FieldSpec.model_validate(item) for item in _BL.required_fields]
_ID_READING = next(
    DocumentTypeSpec.model_validate(item).reading
    for item in _BL.required_documents
    if item["type_key"] == "id_copy"
)
_CARD = ["השם הפרטי", "דנה", "שם המשפחה", "כהן", "מספר הזהות", "1 0000000 9"]


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


def _picture(fmt: str, mark: int = 0) -> bytes:
    image = Image.new("RGB", (320, 120), "white")
    ImageDraw.Draw(image).rectangle((10 + mark, 10, 120 + mark, 60), outline="black", width=3)
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


def _pdf(lines: list[str]) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_font(fontname="rubik", fontfile=str(_FONT))
    y = 72.0
    for line in lines:
        page.insert_textbox(pymupdf.Rect(72, y, 520, y + 24), line, fontname="rubik", fontsize=14)
        y += 32
    data = document.tobytes()
    document.close()
    return data


def _open(client: TestClient) -> str:
    created = client.post("/cases", json={"name": "BL 6101", "process_key": "bl_6101", "client_name": "דנה"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _upload(client: TestClient, case_id: str, name: str, data: bytes, mime: str, **drawer: str):
    return client.post(f"/cases/{case_id}/upload", files=[("files", (name, data, mime))], data=drawer)


def _identified(client: TestClient, case_id: str) -> dict[str, str]:
    gap = client.get(f"/cases/{case_id}").json()["gap"]
    assert gap["in_progress"] == []
    return {item["filename"]: item["document_type"] for item in gap["identified"]}


def _stored(tmp_path: Path, name: str) -> tuple[str, str, str]:
    connection = sqlite3.connect(tmp_path / "test.db")
    row = connection.execute(
        "SELECT mime_type, storage_path, role FROM documents WHERE original_filename = ?", (name,)
    ).fetchone()
    connection.close()
    return row


def test_the_type_is_read_from_the_bytes_not_the_name() -> None:
    assert detect_mime(_picture("PNG")[:16]) == "image/png"
    assert detect_mime(_picture("GIF")[:16]) == "image/gif"
    assert detect_mime(_picture("BMP")[:16]) == "image/bmp"
    assert detect_mime(_picture("WEBP")[:16]) == "image/webp"
    assert detect_mime(b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00") == "image/heic"
    assert detect_mime(b"MZ\x90\x00 an executable") is None


def test_a_screenshot_lands_in_the_drawer_it_was_dropped_on(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    uploaded = _upload(client, case_id, "screen.png", _picture("PNG"), "image/png", document_type="id_copy")
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["accepted_filenames"] == ["screen.png"]
    workspace = client.get(f"/cases/{case_id}").json()
    assert _identified(client, case_id) == {"screen.png": "id_copy"}
    assert workspace["gap"]["unrecognized"] == []
    assert workspace["case"]["status"] != "processing"
    skips = [item["reason"] for reading in workspace["readings"] for item in reading["skips"]]
    assert skips and set(skips) == {"no_text_layer"}
    assert workspace["field_values"] == {}


def test_gif_bmp_and_a_nameless_paste_are_accepted(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    for name, fmt, mark in (("a.gif", "GIF", 0), ("b.bmp", "BMP", 20), ("pasted", "PNG", 40)):
        uploaded = _upload(
            client, case_id, name, _picture(fmt, mark), "application/octet-stream", document_type="proof_of_address"
        )
        assert uploaded.status_code == 200, uploaded.text
        assert uploaded.json()["rejected"] == []
    assert set(_identified(client, case_id)) == {"a.gif", "b.bmp", "pasted"}
    for name in ("a.gif", "b.bmp", "pasted"):
        mime, key, _role = _stored(tmp_path, name)
        assert mime == "image/png"
        assert key.endswith(".png")


def test_a_file_that_is_neither_is_refused_by_name(client: TestClient) -> None:
    case_id = _open(client)
    uploaded = _upload(client, case_id, "notes.png", b"just some words, not a picture", "image/png")
    assert uploaded.status_code == 200, uploaded.text
    assert [item["filename"] for item in uploaded.json()["rejected"]] == ["notes.png"]
    heic = _upload(client, case_id, "phone.heic", b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64, "image/heic")
    assert "HEIC" in heic.json()["rejected"][0]["reason"]


def test_an_unknown_drawer_is_refused(client: TestClient) -> None:
    case_id = _open(client)
    wrong = _upload(client, case_id, "a.png", _picture("PNG"), "image/png", document_type="passport_scan")
    assert wrong.status_code == 400, wrong.text
    role = _upload(client, case_id, "a.png", _picture("PNG"), "image/png", role="template")
    assert role.status_code == 400, role.text


def test_the_same_file_again_moves_to_the_new_drawer(client: TestClient) -> None:
    case_id = _open(client)
    data = _picture("PNG")
    first = _upload(client, case_id, "bill.png", data, "image/png")
    assert first.status_code == 200, first.text
    workspace = client.get(f"/cases/{case_id}").json()
    assert [item["filename"] for item in workspace["gap"]["unrecognized"]] == ["bill.png"]

    again = _upload(client, case_id, "bill-copy.png", data, "image/png", document_type="proof_of_address")
    assert again.status_code == 200, again.text
    assert again.json()["skipped_duplicates"] == ["bill-copy.png"]
    assert again.json()["accepted_filenames"] == []
    assert again.json()["workspace"]["gap"]["unrecognized"] == []
    assert _identified(client, case_id) == {"bill.png": "proof_of_address"}

    moved = _upload(client, case_id, "bill.png", data, "image/png", document_type="bank_confirmation")
    assert moved.status_code == 200, moved.text
    assert _identified(client, case_id) == {"bill.png": "bank_confirmation"}


def test_a_biometric_card_fills_the_three_identity_slots(client: TestClient) -> None:
    case_id = _open(client)
    uploaded = _upload(client, case_id, "card.pdf", _pdf(_CARD), "application/pdf", document_type="id_copy")
    assert uploaded.status_code == 200, uploaded.text
    workspace = client.get(f"/cases/{case_id}").json()
    assert workspace["field_values"] == {"first_name": "דנה", "last_name": "כהן", "national_id": "100000009"}
    assert {item["source"] for item in workspace["field_sources"].values()} == {"document"}


def test_a_spaced_number_is_one_id_and_two_numbers_stay_a_doubt() -> None:
    one = read_document(_ID_READING, "\n".join(_CARD), _FIELDS, set())
    assert {item.slot_key: item.value for item in one.proposals}["national_id"] == "100000009"
    unlabeled = [line for line in _CARD if line != "מספר הזהות"]
    two = read_document(_ID_READING, "\n".join([*unlabeled, "2 0000000 8"]), _FIELDS, set())
    doubt = next(item for item in two.proposals if item.slot_key == "national_id")
    assert (doubt.value, doubt.reason) == (None, "ambiguous_match")
    phone = read_document(_ID_READING, "טלפון 050 1234567 8", _FIELDS, set())
    assert all(item.value is None for item in phone.proposals if item.slot_key == "national_id")


def _read(lines: list[str]) -> dict[str, tuple[str | None, str | None]]:
    outcome = read_document(_ID_READING, "\n".join(lines), _FIELDS, set())
    return {item.slot_key: (item.value, item.reason) for item in outcome.proposals}


def test_a_label_printed_in_two_languages_is_still_the_label() -> None:
    card = [
        "שם המשפחה اسم العائلة",
        "כהן",
        "השם הפרטי الاسم الشخصي",
        "דנה",
        "מספר הזהות رقم الهوية",
        "1 0000000 9",
    ]
    expected = {"first_name": ("דנה", None), "last_name": ("כהן", None), "national_id": ("100000009", None)}
    assert _read(card) == expected
    # Arabic first, English beside the Hebrew, and the value on the label's own line.
    assert _read(["اسم العائلة שם המשפחה", "כהן", "השם הפרטי / Given name", "דנה", "1 0000000 9"]) == expected
    assert _read(["שם המשפחה اسم العائلة כהן", "השם הפרטי الاسم الشخصي: דנה", "1 0000000 9"]) == expected


def test_a_translation_is_never_taken_for_the_value() -> None:
    alone = _read(["שם המשפחה اسم العائلة", "השם הפרטי الاسم الشخصي"])
    assert alone["last_name"] == (None, "label_not_found")
    assert alone["first_name"] == (None, "label_not_found")
    english = _read(["שם המשפחה Surname", "השם הפרטי Given name", "דנה"])
    assert english["last_name"] == (None, "label_not_found")
    assert english["first_name"] == ("דנה", None)
    two = _read(["שם המשפחה اسم العائلة", "כהן", "שם המשפחה", "לוי"])
    assert two["last_name"] == (None, "ambiguous_match")


def test_the_card_number_does_not_cast_doubt_on_the_labeled_id() -> None:
    card = [
        "השם הפרטי الاسم الشخصي",
        "דנה",
        "שם המשפחה اسم العائلة",
        "כהן",
        "מספר הזהות, رقم الهوية",
        "1 0000000 9",
        "שם האב اسم الاب",
        "יעקב",
        "מספר הכרטיס رقم البطاقة",
        "200000008",
    ]
    expected = {"first_name": ("דנה", None), "last_name": ("כהן", None), "national_id": ("100000009", None)}
    assert _read(card) == expected
    # The same number printed again, spaced or not, is still one number.
    assert _read([*card, "100000009", "מספר הזהות", "100000009"]) == expected
    # Two different numbers under the label are a doubt.
    assert _read([*card, "מספר הזהות", "2 0000000 8"])["national_id"] == (None, "ambiguous_match")


_ADDRESS_READING = next(
    DocumentTypeSpec.model_validate(item).reading
    for item in _BL.required_documents
    if item["type_key"] == "proof_of_address"
)
_ADDRESS = {"street": ("הדקל", None), "house_number": ("17", None), "city": ("תל אביב - יפו", None)}


def _read_bill(lines: list[str]) -> dict[str, tuple[str | None, str | None]]:
    outcome = read_document(_ADDRESS_READING, "\n".join(lines), _FIELDS, set())
    return {item.slot_key: (item.value, item.reason) for item in outcome.proposals}


@pytest.mark.parametrize(
    "lines",
    [
        ["1. פרטי הנכס", "כתובת הנכס הדקל 17 תל אביב - יפו", 'שטח הנכס 50 מ"ר', "מספר הנכס 1000000001"],
        ["כתובת הנכס: הדקל 17, תל אביב - יפו"],
        ["כתובת הנכס", "הדקל 17 תל אביב - יפו", 'שטח הנכס 50 מ"ר'],
        ["| כתובת הנכס | הדקל 17 תל אביב - יפו |", '| שטח הנכס | 50 מ"ר |'],
        ["| שדה | ערך |", "|---|---|", "| **כתובת הנכס** | הדקל 17 תל אביב - יפו |"],
        ["**כתובת הנכס** הדקל 17 תל אביב - יפו"],
        ["- **כתובת הנכס:** הדקל 17 תל אביב - יפו"],
        ["כתובת הנכס הדקל 17 תל אביב - יפו 6100000"],
    ],
)
def test_one_address_line_fills_street_house_number_and_town(lines: list[str]) -> None:
    assert _read_bill(lines) == _ADDRESS


def test_an_address_line_that_does_not_split_stays_with_the_office() -> None:
    # No house number: the line is kept whole as the street, and nothing is guessed for the town.
    whole = _read_bill(["כתובת הנכס קיבוץ הדקל"])
    assert whole["street"] == ("קיבוץ הדקל", None)
    assert whole["city"][0] is None and whole["house_number"][0] is None
    short = _read_bill(["כתובת: רחוב הדקל 17"])
    assert (short["street"], short["house_number"]) == (("הדקל", None), ("17", None))
    assert short["city"][0] is None
    # Two properties on one bill are a doubt for every piece.
    two = _read_bill(["כתובת הנכס הדקל 17 תל אביב - יפו", "כתובת הנכס הברוש 4 חיפה"])
    assert {value for value, _reason in two.values()} == {None}
    # The separate labels still read as before, and agree with the address line.
    both = _read_bill(["רחוב", "הדקל", "עיר", "חיפה", "כתובת הנכס הדקל 17 חיפה"])
    assert both == {"street": ("הדקל", None), "house_number": ("17", None), "city": ("חיפה", None)}


def test_a_bank_name_that_begins_with_the_word_bank_is_one_value() -> None:
    reading = next(
        DocumentTypeSpec.model_validate(item).reading
        for item in _BL.required_documents
        if item["type_key"] == "bank_confirmation"
    )
    lines = ["שם הבנק", "בנק לדוגמה", "קוד בנק", "99", "מספר סניף", "123", "מספר חשבון", "456789"]
    outcome = read_document(reading, "\n".join(lines), _FIELDS, set())
    assert {item.slot_key: (item.value, item.reason) for item in outcome.proposals} == {
        "bank_name": ("בנק לדוגמה", None),
        "bank_branch": ("123", None),
        "bank_account": ("456789", None),
    }


def test_a_form_uploaded_as_a_form_is_the_form(client: TestClient, tmp_path: Path) -> None:
    from tests.test_bl6101_sanity_drill import _bl_form

    case_id = _open(client)
    form = _bl_form(tmp_path / "bl.pdf").read_bytes()
    uploaded = _upload(client, case_id, "bl.pdf", form, "application/pdf", role="form")
    assert uploaded.status_code == 200, uploaded.text
    workspace = client.get(f"/cases/{case_id}").json()
    assert workspace["gap"]["unrecognized"] == []
    forms = client.get(f"/cases/{case_id}/intake").json()["forms"]
    assert [(item["filename"], item["role"]) for item in forms] == [("bl.pdf", "form")]


def test_a_picture_cannot_be_the_form(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    uploaded = _upload(client, case_id, "form.png", _picture("PNG"), "image/png", role="form")
    assert uploaded.status_code == 200, uploaded.text
    assert _stored(tmp_path, "form.png")[2] == "evidence"
    document_id = client.get(f"/cases/{case_id}").json()["gap"]["unrecognized"][0]["document_id"]
    marked = client.put(f"/cases/{case_id}/documents/{document_id}/role", json={"role": "form"})
    assert marked.status_code == 409, marked.text
    assert "PDF" in marked.text


def test_a_reader_that_never_answers_does_not_hold_the_case(client: TestClient) -> None:
    class _Silent:
        calls = 0

        async def transcribe(self, images: list) -> str:
            self.calls += 1
            await asyncio.sleep(30)
            return "late"

    silent = _Silent()
    pipeline = client.app.state.container.pipeline
    pipeline._transcriber = silent
    pipeline._ai_timeout = 0.2
    case_id = _open(client)
    uploaded = _upload(client, case_id, "slow.png", _picture("PNG"), "image/png", document_type="id_copy")
    assert uploaded.status_code == 200, uploaded.text
    assert silent.calls == 1
    workspace = client.get(f"/cases/{case_id}").json()
    assert _identified(client, case_id) == {"slow.png": "id_copy"}
    assert workspace["case"]["status"] != "processing"
    assert workspace["field_values"] == {}
