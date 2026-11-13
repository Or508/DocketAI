"""Fail-closed reading: one unambiguous value, or the slot stays with the office."""

import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

import pymupdf
from fastapi.testclient import TestClient

from app.catalog.processes import PROCESSES
from app.domain.slot_reading import apply_proposals, read_document, retract_document
from app.schemas.process import DocumentReading, FieldSpec

_FIELDS = [
    FieldSpec.model_validate(item)
    for item in next(process for process in PROCESSES if process.key == "onboarding").required_fields
]
_ID = "100000009"
_OTHER = "100000017"
_IDENTITY = DocumentReading.model_validate(
    {
        "enabled": True,
        "one_person": True,
        "rules": [
            {
                "kind": "composite",
                "slot_key": "full_name",
                "parts": [
                    {"labels": ["שם פרטי"]},
                    {"labels": ["שם משפחה"]},
                ],
            },
            {"kind": "labeled", "slot_key": "full_name", "labels": ["שם מלא"]},
            {"kind": "unique", "slot_key": "national_id"},
        ],
    }
)


def _values(text: str, case_ids: set[str] | None = None) -> dict[str, str]:
    outcome = read_document(_IDENTITY, text, _FIELDS, case_ids or set())
    writes, _skips, _conflicts = apply_proposals({}, outcome.proposals)
    return writes


def test_a_labeled_name_and_one_id_fill_empty_slots() -> None:
    assert _values(f"שם מלא: דנה כהן\n{_ID}") == {"full_name": "דנה כהן", "national_id": _ID}


def test_a_split_name_is_joined_only_when_both_parts_are_labeled() -> None:
    assert _values("שם פרטי: דנה\nשם משפחה: כהן\n" + _ID)["full_name"] == "דנה כהן"
    assert "full_name" not in _values("שם פרטי: דנה\n" + _ID)


def test_reversed_hebrew_and_the_next_line_still_match() -> None:
    visual = "שם מלא: דנה כהן"[::-1]
    assert _values(f"{visual}\n{_ID}")["full_name"] == "דנה כהן"
    assert _values(f"שם מלא\nדנה כהן\n{_ID}")["full_name"] == "דנה כהן"


def test_doubt_proposes_nothing() -> None:
    two_ids = read_document(_IDENTITY, f"שם מלא: דנה כהן\n{_ID}\n{_OTHER}", _FIELDS, set())
    assert all(item.slot_key != "national_id" or item.reason == "ambiguous_match" for item in two_ids.proposals)
    shared = DocumentReading.model_validate(
        {"enabled": True, "one_person": False, "rules": [{"kind": "unique", "slot_key": "national_id"}]}
    )
    outcome = read_document(shared, _ID, _FIELDS, set())
    assert outcome.proposals[0].reason == "label_not_found"
    mismatch = read_document(_IDENTITY, f"שם מלא: נועה לוי\n{_OTHER}", _FIELDS, {_ID})
    assert mismatch.blocked == "id_mismatch"


def test_a_different_value_is_kept_as_a_conflict_and_reclassify_drops_the_old_one() -> None:
    outcome = read_document(_IDENTITY, f"שם מלא: נועה לוי\n{_OTHER}", _FIELDS, set())
    _writes, _skips, conflicts = apply_proposals({"full_name": "דנה כהן", "national_id": _ID}, outcome.proposals)
    assert ("full_name", "נועה לוי") in conflicts
    values, sources = retract_document(
        {"full_name": "דנה כהן", "national_id": _ID},
        {
            "full_name": {"source": "document", "document_id": "doc-1"},
            "national_id": {"source": "office", "document_id": None},
        },
        "doc-1",
    )
    assert "full_name" not in values
    assert values["national_id"] == _ID
    assert "full_name" not in sources


def _declared_reading(type_key: str, process_key: str = "onboarding") -> DocumentReading:
    process = next(process for process in PROCESSES if process.key == process_key)
    for item in [*process.required_documents, *process.optional_documents]:
        raw = item if isinstance(item, dict) else item.model_dump()
        if raw["type_key"] == type_key:
            return DocumentReading.model_validate(raw["reading"])
    raise AssertionError(f"{type_key} is not declared in {process_key}")


def _declared_address_reading() -> DocumentReading:
    return _declared_reading("proof_of_address")


_ADDRESS = _declared_address_reading()
_TAX = _declared_reading("tax_form")
_START = "2026-12-01"


def _tax(text: str) -> tuple[dict[str, tuple[str | None, str | None]], dict[str, str]]:
    outcome = read_document(_TAX, text, _FIELDS, set())
    assert outcome.blocked is None
    writes, _skips, conflicts = apply_proposals({}, outcome.proposals)
    assert conflicts == []
    return {item.slot_key: (item.value, item.reason) for item in outcome.proposals}, writes


def test_tax_form_is_declared_off_with_two_labeled_rules() -> None:
    assert _TAX.enabled is False
    assert _TAX.one_person is False
    assert [(rule.kind, rule.slot_key, rule.labels) for rule in _TAX.rules] == [
        ("labeled", "national_id", ["מספר זהות", "תעודת זהות", "national id"]),
        ("labeled", "start_date", ["תאריך תחילת עבודה", "start date"]),
    ]


def test_one_labeled_id_and_one_labeled_start_date_fill_empty_slots() -> None:
    proposals, writes = _tax(f"טופס 101\nמספר זהות: {_ID}\nתאריך תחילת עבודה: 01/12/2026")
    assert proposals == {"national_id": (_ID, None), "start_date": (_START, None)}
    assert writes == {"national_id": _ID, "start_date": _START}


def test_two_different_ids_on_a_tax_form_are_ambiguous_and_write_nothing() -> None:
    proposals, writes = _tax(f"מספר זהות: {_ID}\nתעודת זהות: {_OTHER}")
    assert proposals["national_id"] == (None, "ambiguous_match")
    assert "national_id" not in writes


def test_two_different_start_dates_are_ambiguous_and_write_nothing() -> None:
    proposals, writes = _tax("תאריך תחילת עבודה: 01/12/2026\nstart date: 15/01/2027")
    assert proposals["start_date"] == (None, "ambiguous_match")
    assert "start_date" not in writes


def test_a_tax_form_without_its_labels_proposes_no_id_and_no_start_date() -> None:
    proposals, writes = _tax(f"טופס 101\n{_ID}\n01/12/2026")
    assert proposals == {
        "national_id": (None, "label_not_found"),
        "start_date": (None, "label_not_found"),
    }
    assert writes == {}


def test_an_address_or_a_name_on_a_tax_form_is_not_proposed() -> None:
    text = (
        "שם מלא: דנה כהן\n"
        "כתובת: הרצל 10 תל אביב\n"
        f"מספר זהות: {_ID}\n"
        "תאריך תחילת עבודה: 01/12/2026"
    )
    proposals, writes = _tax(text)
    assert set(proposals) == {rule.slot_key for rule in _TAX.rules} == {"national_id", "start_date"}
    assert writes == {"national_id": _ID, "start_date": _START}


def test_proof_of_address_is_declared_off_with_one_address_rule() -> None:
    assert _ADDRESS.enabled is False
    assert _ADDRESS.one_person is False
    assert [(rule.kind, rule.slot_key) for rule in _ADDRESS.rules] == [("labeled", "address_he")]
    assert _ADDRESS.rules[0].labels == ["כתובת הנכס", "כתובת", "כתובת מגורים", "address"]


def test_a_property_address_label_is_proposed_for_the_address_slot() -> None:
    outcome = read_document(_ADDRESS, "כתובת הנכס: הרצל 10 תל אביב", _FIELDS, set())
    assert outcome.blocked is None
    assert [(item.slot_key, item.value) for item in outcome.proposals] == [("address_he", "הרצל 10 תל אביב")]
    writes, _skips, conflicts = apply_proposals({}, outcome.proposals)
    assert writes == {"address_he": "הרצל 10 תל אביב"}
    assert conflicts == []


def test_an_address_on_the_same_line_as_its_label_is_proposed() -> None:
    outcome = read_document(_ADDRESS, "כתובת הנכס הרצל 15, תל אביב", _FIELDS, set())
    assert [(item.slot_key, item.value) for item in outcome.proposals] == [("address_he", "הרצל 15, תל אביב")]
    writes, _skips, _conflicts = apply_proposals({}, outcome.proposals)
    assert writes == {"address_he": "הרצל 15, תל אביב"}


def test_a_following_account_column_is_not_part_of_the_address() -> None:
    text = "כתובת הנכס הרצל 15, תל אביב מספר חשבון לקוח 12345678"
    outcome = read_document(_ADDRESS, text, _FIELDS, set())
    assert [(item.slot_key, item.value) for item in outcome.proposals] == [("address_he", "הרצל 15, תל אביב")]
    writes, _skips, _conflicts = apply_proposals({}, outcome.proposals)
    assert writes == {"address_he": "הרצל 15, תל אביב"}


def test_a_house_number_word_stays_inside_the_address() -> None:
    outcome = read_document(_ADDRESS, "כתובת הנכס הרצל מספר 15 תל אביב", _FIELDS, set())
    assert [(item.slot_key, item.value) for item in outcome.proposals] == [
        ("address_he", "הרצל מספר 15 תל אביב")
    ]


def test_a_property_address_and_a_different_home_address_are_ambiguous_and_write_nothing() -> None:
    text = "כתובת הנכס: הרצל 10 תל אביב\nכתובת מגורים: ויצמן 5 חיפה"
    outcome = read_document(_ADDRESS, text, _FIELDS, set())
    assert [(item.slot_key, item.value, item.reason) for item in outcome.proposals] == [
        ("address_he", None, "ambiguous_match")
    ]
    writes, _skips, conflicts = apply_proposals({}, outcome.proposals)
    assert writes == {}
    assert conflicts == []


def test_one_labeled_address_is_proposed_for_the_address_slot() -> None:
    outcome = read_document(_ADDRESS, "חשבון ארנונה\nכתובת: הרצל 10 תל אביב", _FIELDS, set())
    assert outcome.blocked is None
    assert [(item.slot_key, item.value) for item in outcome.proposals] == [("address_he", "הרצל 10 תל אביב")]
    writes, _skips, _conflicts = apply_proposals({}, outcome.proposals)
    assert writes == {"address_he": "הרצל 10 תל אביב"}


def test_two_different_addresses_are_ambiguous_and_write_nothing() -> None:
    text = "כתובת: הרצל 10 תל אביב\nכתובת מגורים: ויצמן 5 חיפה"
    outcome = read_document(_ADDRESS, text, _FIELDS, set())
    assert [(item.slot_key, item.value, item.reason) for item in outcome.proposals] == [
        ("address_he", None, "ambiguous_match")
    ]
    writes, _skips, conflicts = apply_proposals({}, outcome.proposals)
    assert writes == {}
    assert conflicts == []


def test_an_id_number_in_an_address_document_is_not_proposed() -> None:
    text = f"כתובת: הרצל 10 תל אביב\nמספר זהות: {_ID}\n{_ID}"
    outcome = read_document(_ADDRESS, text, _FIELDS, set())
    assert {item.slot_key for item in outcome.proposals} == {"address_he"}
    assert outcome.blocked is None
    writes, _skips, _conflicts = apply_proposals({}, outcome.proposals)
    assert writes == {"address_he": "הרצל 10 תל אביב"}


def test_text_without_an_address_label_proposes_no_address() -> None:
    outcome = read_document(_ADDRESS, f"חשבון ארנונה\nהרצל 10 תל אביב\n{_ID}", _FIELDS, set())
    assert [(item.slot_key, item.value, item.reason) for item in outcome.proposals] == [
        ("address_he", None, "label_not_found")
    ]
    writes, _skips, _conflicts = apply_proposals({}, outcome.proposals)
    assert writes == {}


_ID_COPY = _declared_reading("id_copy")


def _id_copy(text: str) -> tuple[dict[str, tuple[str | None, str | None]], dict[str, str]]:
    outcome = read_document(_ID_COPY, text, _FIELDS, set())
    assert outcome.blocked is None
    writes, _skips, conflicts = apply_proposals({}, outcome.proposals)
    assert conflicts == []
    return {item.slot_key: (item.value, item.reason) for item in outcome.proposals}, writes


def test_id_copy_is_declared_off_for_one_person_with_three_rules_in_order() -> None:
    assert _ID_COPY.enabled is False
    assert _ID_COPY.one_person is True
    assert [
        (rule.kind, rule.slot_key, rule.labels, [part.labels for part in rule.parts])
        for rule in _ID_COPY.rules
    ] == [
        (
            "composite",
            "full_name",
            [],
            [["שם פרטי", "first name"], ["שם משפחה", "last name", "family name"]],
        ),
        ("labeled", "full_name", ["שם מלא", "full name", "full legal name"], []),
        ("unique", "national_id", [], []),
    ]


def test_a_declared_id_copy_fills_a_labeled_full_name_and_one_valid_id() -> None:
    proposals, writes = _id_copy(f"תעודת זהות\nשם מלא: דנה כהן\n{_ID}")
    assert proposals == {"full_name": ("דנה כהן", None), "national_id": (_ID, None)}
    assert writes == {"full_name": "דנה כהן", "national_id": _ID}


def test_a_declared_id_copy_joins_first_and_family_name_only_when_both_are_labeled() -> None:
    proposals, writes = _id_copy(f"שם פרטי: דנה\nשם משפחה: כהן\n{_ID}")
    assert proposals["full_name"] == ("דנה כהן", None)
    assert writes == {"full_name": "דנה כהן", "national_id": _ID}

    proposals, writes = _id_copy(f"שם פרטי: דנה\n{_ID}")
    assert proposals["full_name"] == (None, "label_not_found")
    assert writes == {"national_id": _ID}


def test_two_different_valid_ids_on_an_id_copy_are_ambiguous_and_write_no_id() -> None:
    proposals, writes = _id_copy(f"שם מלא: דנה כהן\n{_ID}\n{_OTHER}")
    assert proposals["national_id"] == (None, "ambiguous_match")
    assert writes == {"full_name": "דנה כהן"}


def test_a_name_without_a_label_on_an_id_copy_proposes_no_full_name() -> None:
    proposals, writes = _id_copy(f"תעודת זהות\nדנה כהן\n{_ID}")
    assert proposals["full_name"] == (None, "label_not_found")
    assert writes == {"national_id": _ID}


def test_an_address_on_an_id_copy_is_not_proposed() -> None:
    proposals, writes = _id_copy(f"שם מלא: דנה כהן\nכתובת: הרצל 10 תל אביב\n{_ID}")
    assert set(proposals) == {rule.slot_key for rule in _ID_COPY.rules} == {"full_name", "national_id"}
    assert writes == {"full_name": "דנה כהן", "national_id": _ID}


def test_two_different_full_names_on_an_id_copy_are_ambiguous_and_keep_the_id() -> None:
    proposals, writes = _id_copy(f"שם מלא: דנה כהן\nfull name: נועה לוי\n{_ID}")
    assert proposals == {"full_name": (None, "ambiguous_match"), "national_id": (_ID, None)}
    assert writes == {"national_id": _ID}


_ESTATE_FIELDS = [
    FieldSpec.model_validate(item)
    for item in next(process for process in PROCESSES if process.key == "real_estate").required_fields
]
_DEED = _declared_reading("title_deed", "real_estate")
_PROPERTY = "הרצל 10 תל אביב"
_PARCEL = "6941/12"


def _deed(text: str) -> tuple[dict[str, tuple[str | None, str | None]], dict[str, str]]:
    outcome = read_document(_DEED, text, _ESTATE_FIELDS, set())
    assert outcome.blocked is None
    writes, _skips, conflicts = apply_proposals({}, outcome.proposals)
    assert conflicts == []
    return {item.slot_key: (item.value, item.reason) for item in outcome.proposals}, writes


def test_title_deed_is_declared_off_with_two_labeled_rules_in_order() -> None:
    assert _DEED.enabled is False
    assert _DEED.one_person is False
    assert [(rule.kind, rule.slot_key, rule.labels) for rule in _DEED.rules] == [
        ("labeled", "property_address_he", ["כתובת הנכס", "כתובת", "property address"]),
        ("labeled", "parcel_number", ["גוש וחלקה", "גוש/חלקה", "parcel"]),
    ]


def test_one_labeled_property_address_and_one_labeled_parcel_fill_empty_slots() -> None:
    proposals, writes = _deed(f"נסח טאבו\nכתובת הנכס: {_PROPERTY}\nגוש וחלקה: {_PARCEL}")
    assert proposals == {"property_address_he": (_PROPERTY, None), "parcel_number": (_PARCEL, None)}
    assert writes == {"property_address_he": _PROPERTY, "parcel_number": _PARCEL}


def test_two_different_property_addresses_are_ambiguous_and_write_no_address() -> None:
    proposals, writes = _deed(f"כתובת הנכס: {_PROPERTY}\nכתובת: ויצמן 5 חיפה\nגוש וחלקה: {_PARCEL}")
    assert proposals["property_address_he"] == (None, "ambiguous_match")
    assert writes == {"parcel_number": _PARCEL}


def test_two_different_parcels_are_ambiguous_and_write_no_parcel() -> None:
    proposals, writes = _deed(f"כתובת הנכס: {_PROPERTY}\nגוש וחלקה: {_PARCEL}\nגוש/חלקה: 7102/45")
    assert proposals["parcel_number"] == (None, "ambiguous_match")
    assert writes == {"property_address_he": _PROPERTY}


def test_a_title_deed_without_its_labels_proposes_no_address_and_no_parcel() -> None:
    proposals, writes = _deed(f"נסח טאבו\n{_PROPERTY}\n{_PARCEL}")
    assert proposals == {
        "property_address_he": (None, "label_not_found"),
        "parcel_number": (None, "label_not_found"),
    }
    assert writes == {}


def test_a_buyer_name_on_a_title_deed_is_not_proposed() -> None:
    text = f"שם הרוכש: דנה כהן\nשם מלא: דנה כהן\nכתובת הנכס: {_PROPERTY}\nגוש וחלקה: {_PARCEL}"
    proposals, writes = _deed(text)
    assert set(proposals) == {rule.slot_key for rule in _DEED.rules} == {"property_address_he", "parcel_number"}
    assert writes == {"property_address_he": _PROPERTY, "parcel_number": _PARCEL}


_BUYER_ID = _declared_reading("id_copy", "real_estate")


def _buyer(text: str) -> tuple[dict[str, tuple[str | None, str | None]], dict[str, str]]:
    outcome = read_document(_BUYER_ID, text, _ESTATE_FIELDS, set())
    assert outcome.blocked is None
    writes, _skips, conflicts = apply_proposals({}, outcome.proposals)
    assert conflicts == []
    return {item.slot_key: (item.value, item.reason) for item in outcome.proposals}, writes


def test_buyer_id_copy_is_declared_off_for_one_person_with_two_name_rules_and_no_id_rule() -> None:
    assert _BUYER_ID.enabled is False
    assert _BUYER_ID.one_person is True
    assert [
        (rule.kind, rule.slot_key, rule.labels, [part.labels for part in rule.parts])
        for rule in _BUYER_ID.rules
    ] == [
        (
            "composite",
            "buyer_name",
            [],
            [["שם פרטי", "first name"], ["שם משפחה", "last name", "family name"]],
        ),
        ("labeled", "buyer_name", ["שם הרוכש", "שם מלא", "full name"], []),
    ]
    assert all(rule.slot_key != "national_id" for rule in _BUYER_ID.rules)


def test_one_labeled_buyer_name_fills_the_empty_slot() -> None:
    proposals, writes = _buyer(f"תעודת זהות\nשם הרוכש: דנה כהן\n{_ID}")
    assert proposals == {"buyer_name": ("דנה כהן", None)}
    assert writes == {"buyer_name": "דנה כהן"}


def test_a_buyer_name_is_joined_only_when_first_and_family_name_are_both_labeled() -> None:
    proposals, writes = _buyer("שם פרטי: דנה\nשם משפחה: כהן")
    assert proposals == {"buyer_name": ("דנה כהן", None)}
    assert writes == {"buyer_name": "דנה כהן"}

    proposals, writes = _buyer("שם פרטי: דנה")
    assert proposals == {"buyer_name": (None, "label_not_found")}
    assert writes == {}


def test_two_different_labeled_buyer_names_are_ambiguous_and_write_nothing() -> None:
    proposals, writes = _buyer("שם הרוכש: דנה כהן\nשם מלא: נועה לוי")
    assert proposals == {"buyer_name": (None, "ambiguous_match")}
    assert writes == {}


def test_a_name_without_a_label_proposes_no_buyer_name() -> None:
    proposals, writes = _buyer(f"תעודת זהות\nדנה כהן\n{_ID}")
    assert proposals == {"buyer_name": (None, "label_not_found")}
    assert writes == {}


def test_a_property_a_parcel_or_a_seller_on_a_buyer_id_copy_is_not_proposed() -> None:
    text = (
        "שם הרוכש: דנה כהן\n"
        "שם המוכר: נועה לוי\n"
        f"כתובת הנכס: {_PROPERTY}\n"
        f"גוש וחלקה: {_PARCEL}\n"
        f"{_ID}"
    )
    proposals, writes = _buyer(text)
    assert set(proposals) == {rule.slot_key for rule in _BUYER_ID.rules} == {"buyer_name"}
    assert writes == {"buyer_name": "דנה כהן"}


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


def _pdf(path: Path, lines: list[str]) -> bytes:
    font = Path(__file__).resolve().parents[1] / "app" / "assets" / "fonts" / "Rubik-Regular.ttf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_font(fontname="rubik", fontfile=str(font))
    y = 72.0
    for line in lines:
        page.insert_textbox(pymupdf.Rect(72, y, 520, y + 24), line, fontname="rubik", fontsize=14)
        y += 32
    document.save(path)
    document.close()
    return path.read_bytes()


def _enable_identity(database: Path) -> None:
    connection = sqlite3.connect(database)
    raw = connection.execute(
        "SELECT required_documents FROM process_definitions WHERE key = 'onboarding'"
    ).fetchone()
    documents = json.loads(raw[0])
    for item in documents:
        if item.get("type_key") == "id_copy":
            item["reading"]["enabled"] = True
    connection.execute(
        "UPDATE process_definitions SET required_documents = ? WHERE key = 'onboarding'",
        (json.dumps(documents, ensure_ascii=False),),
    )
    connection.commit()
    connection.close()


def test_reading_stays_off_until_the_type_is_enabled(client: TestClient, tmp_path: Path) -> None:
    created = client.post("/cases", json={"name": "Quiet", "process_key": "onboarding", "client_name": "Dana"})
    case_id = created.json()["id"]
    uploaded = client.post(
        f"/cases/{case_id}/upload",
        files=[("files", ("id.pdf", _pdf(tmp_path / "id.pdf", ["שם מלא: דנה כהן", _ID]), "application/pdf"))],
    )
    assert uploaded.status_code == 200, uploaded.text
    document_id = next(item["document_id"] for item in client.get(f"/cases/{case_id}").json()["gap"]["unrecognized"])
    classified = client.post(
        f"/cases/{case_id}/classify-manual",
        json={"document_id": document_id, "document_type": "id_copy"},
    )
    assert classified.status_code == 200, classified.text
    body = classified.json()
    assert "national_id" not in body["field_values"]
    assert body["readings"][0]["enabled"] is False


def test_an_enabled_identity_fills_once_and_a_second_file_does_not_replace_it(
    client: TestClient, tmp_path: Path
) -> None:
    _enable_identity(tmp_path / "test.db")
    created = client.post("/cases", json={"name": "Read", "process_key": "onboarding", "client_name": "Dana"})
    case_id = created.json()["id"]
    first = client.post(
        f"/cases/{case_id}/upload",
        files=[("files", ("id.pdf", _pdf(tmp_path / "id.pdf", ["שם מלא: דנה כהן", _ID]), "application/pdf"))],
    )
    assert first.status_code == 200, first.text
    document_id = next(item["document_id"] for item in client.get(f"/cases/{case_id}").json()["gap"]["unrecognized"])
    classified = client.post(
        f"/cases/{case_id}/classify-manual",
        json={"document_id": document_id, "document_type": "id_copy"},
    )
    assert classified.status_code == 200, classified.text
    body = classified.json()
    assert body["field_values"]["full_name"] == "דנה כהן"
    assert body["field_values"]["national_id"] == _ID
    assert body["field_sources"]["full_name"]["source"] == "document"
    assert body["readings"][0]["accepted"]

    second = client.post(
        f"/cases/{case_id}/upload",
        files=[("files", ("other.pdf", _pdf(tmp_path / "other.pdf", ["שם מלא: נועה לוי", _OTHER]), "application/pdf"))],
    )
    assert second.status_code == 200, second.text
    other_id = next(item["document_id"] for item in client.get(f"/cases/{case_id}").json()["gap"]["unrecognized"])
    kept = client.post(
        f"/cases/{case_id}/classify-manual",
        json={"document_id": other_id, "document_type": "id_copy"},
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["field_values"]["full_name"] == "דנה כהן"
    assert kept.json()["field_values"]["national_id"] == _ID
    assert kept.json()["readings"][-1]["blocked"] == "id_mismatch"
