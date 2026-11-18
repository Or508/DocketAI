"""The office's profession, and the private dental clinic's package: consents and the medical questionnaire."""

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.catalog.dental import BOTOX, CT, DENTAL_KEYS, QUESTIONNAIRE, TREATMENT_PLAN
from app.catalog.processes import PROCESSES
from app.db.compat import _add_missing_case_columns
from app.domain.text_layout import contains_hebrew
from app.schemas.process import FieldSpec
from app.services.dental_forms import dental_form_builder
from app.services.flat_form import FlatProfile, read_flat_anchors, signature_box
from app.services.fonts import resolve_hebrew_font
from app.services.pdf_filler import _readback_matches
from tests.support import SignedOut, authenticate
from tests.test_bl6101_sanity_drill import _ID, _pdf, _set, _sign_body
from tests.test_smart_upload_and_real_estate import (  # noqa: F401  (client is the fixture)
    _ID_LINES,
    _drop,
    _forms,
    _timeline,
    client,
)

_SEEDS = {process.key: process for process in PROCESSES if process.key in DENTAL_KEYS}
_TYPED = {
    BOTOX: {"phone": "0501234567", "treatment_area": "מצח וקמטי צחוק", "product_name": "Botox", "units": "20",
            "treating_doctor": "ד\"ר נועה לוי", "treatment_date": "2026-12-01"},
    CT: {"phone": "0501234567", "scan_area": "לסת עליונה", "referring_doctor": "ד\"ר נועה לוי", "scan_date": "2026-12-02"},
    TREATMENT_PLAN: {"phone": "0501234567", "treatment_plan": "שני שתלים וכתר", "total_price": "14500",
                     "payment_terms": "שלושה תשלומים", "treating_doctor": "ד\"ר נועה לוי", "plan_date": "2026-11-20"},
    QUESTIONNAIRE: {"phone": "0501234567", "birth_date": "1990-05-14", "medications": "אין", "allergies": "פניצילין",
                    "chronic_conditions": "אין"},
}


def _fields(key: str) -> list[FieldSpec]:
    return [FieldSpec.model_validate(item) for item in _SEEDS[key].required_fields]


def _blank(key: str) -> bytes:
    font = resolve_hebrew_font(None)
    assert font is not None
    return dental_form_builder(key)(font)


def _make_clinic(client: TestClient, headers: dict[str, str] | None = None) -> dict:
    changed = client.put("/organization/profession", headers=headers, json={"profession": "dental_clinic"})
    assert changed.status_code == 200, changed.text
    return changed.json()


def _open(client: TestClient, key: str) -> str:
    created = client.post("/cases", json={"name": "מטופל", "process_key": key, "client_name": "דנה כהן"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


# The office's profession


def test_an_office_is_a_law_office_until_it_chooses_otherwise(client: TestClient) -> None:
    me = client.get("/auth/me").json()
    assert (me["profession"], me["profession_label_he"], me["client_term_he"], me["case_term_he"]) == (
        "law", "משרד עורכי דין", "לקוח", "תיק",
    )
    office = client.get("/organization").json()
    assert office["profession"]["key"] == "law"
    assert [item["key"] for item in office["professions"]] == ["law", "accounting", "dental_clinic"]

    clinic = _make_clinic(client)
    assert clinic["profession"] == {
        "key": "dental_clinic", "label_he": "מרפאת שיניים", "client_term_he": "מטופל", "case_term_he": "תיק מטופל",
    }
    me = client.get("/auth/me").json()
    assert (me["profession"], me["client_term_he"]) == ("dental_clinic", "מטופל")
    # Setting the same profession again changes nothing and still answers.
    assert _make_clinic(client) == clinic

    assert client.put("/organization/profession", json={"profession": "astronaut"}).status_code == 400
    assert client.get("/auth/me").json()["profession"] == "dental_clinic"

    # Another office keeps its own profession, and a stranger cannot change any.
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    assert client.get("/auth/me", headers=headers).json()["profession"] == "law"
    with SignedOut(client) as anonymous:
        assert anonymous.get("/organization").status_code == 401
        assert anonymous.request("PUT", "/organization/profession", json={"profession": "law"}).status_code == 401


def test_the_catalog_shows_each_profession_its_own_processes(client: TestClient) -> None:
    every = client.get("/processes").json()
    by_key = {item["key"]: item for item in every}
    assert set(DENTAL_KEYS) <= set(by_key)
    assert all(by_key[key]["professions"] == ["dental_clinic"] for key in DENTAL_KEYS)
    assert by_key["employee_onboarding"]["professions"] == ["law", "accounting"]

    dental = client.get("/processes", params={"profession": "dental_clinic"}).json()
    assert sorted(item["key"] for item in dental) == sorted(DENTAL_KEYS)
    law = {item["key"] for item in client.get("/processes", params={"profession": "law"}).json()}
    assert law == {"bl_6101", "real_estate", "onboarding", "employee_onboarding"}
    assert client.get("/processes", params={"profession": "astronaut"}).status_code == 400

    templates = {item["process_type"]: item for item in client.get("/templates").json()}
    assert templates[BOTOX]["title_he"] == "הסכמה מדעת להזרקת בוטוקס"
    assert templates[CT]["title_he"] == "הסכמה לצילום CT"
    assert all(templates[key]["form_source"] == "official_blank" for key in DENTAL_KEYS)


def test_an_office_from_before_professions_becomes_a_law_office(tmp_path: Path) -> None:
    database = tmp_path / "old.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE organizations (id CHAR(32) PRIMARY KEY, name VARCHAR(160), created_at DATETIME)")
    connection.execute("INSERT INTO organizations (id, name) VALUES ('a', 'Old office')")
    connection.commit()
    connection.close()

    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as sync_conn:
        _add_missing_case_columns(sync_conn)
        _add_missing_case_columns(sync_conn)  # a second boot adds nothing
    with engine.connect() as sync_conn:
        assert "profession" in {column["name"] for column in inspect(sync_conn).get_columns("organizations")}
    engine.dispose()
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT profession FROM organizations").fetchall() == [("law",)]
    connection.close()


# The drawn forms


@pytest.mark.parametrize("key", DENTAL_KEYS)
def test_each_dental_blank_is_stable_with_a_cell_for_every_field(key: str, tmp_path: Path) -> None:
    first = _blank(key)
    assert first == _blank(key)
    path = tmp_path / f"{key}.pdf"
    path.write_bytes(first)
    document = pymupdf.open(path)
    try:
        assert document.page_count == 2
        assert not any(page.first_widget for page in document)
        # Both pages carry the form's own title, never a section name.
        titles = [page.get_text("text", clip=pymupdf.Rect(0, 40, page.rect.width, 75)).strip() for page in document]
        assert titles[0] == titles[1]
    finally:
        document.close()
    seed = _SEEDS[key]
    anchors = read_flat_anchors(path, _fields(key), FlatProfile.from_layout(seed.layout))
    assert sorted(anchor["slot_key"] for anchor in anchors) == sorted(spec.key for spec in _fields(key))
    # Every value goes in the cell under its label; the ID number goes one digit per box.
    assert {anchor["slot_key"]: anchor["target"] for anchor in anchors if anchor["target"] != "cell_below"} == {
        "national_id": "comb"
    }
    assert all(anchor["page"] == 0 for anchor in anchors)
    page, rect = signature_box(path, seed.layout["signature_labels"])
    assert page == 1 and rect[2] - rect[0] > 150


# A patient's case, start to finish


@pytest.mark.parametrize("key", DENTAL_KEYS)
def test_a_patient_case_reads_the_id_fills_the_form_and_signs(key: str, client: TestClient, tmp_path: Path) -> None:
    _make_clinic(client)
    case_id = _open(client, key)
    loaded = client.post(f"/cases/{case_id}/load-default-form")
    assert loaded.status_code == 200, loaded.text
    forms = _forms(client, case_id)
    assert [(item["filename"], item["role"]) for item in forms] == [(f"{key}.pdf", "form")]
    assert forms[0]["bound"] == len(_fields(key))

    # The patient's name and ID number come from the ID card.
    dropped = _drop(client, case_id, [("id.pdf", _pdf(tmp_path / "id.pdf", _ID_LINES))])
    assert dropped.status_code == 200, dropped.text
    body = dropped.json()
    assert body["field_values"]["patient_name"] == "דנה כהן"
    assert body["field_values"]["national_id"] == _ID
    assert body["field_sources"]["national_id"]["source"] == "document"

    for slot, value in _TYPED[key].items():
        body = _set(client, case_id, slot, value)
    assert body["ready_to_sign"] is True, body["signing_blockers"]

    # The draft shows every value in its own cell on the clinic's form.
    preview = client.get(f"/cases/{case_id}/documents/{forms[0]['document_id']}/filled-preview")
    assert preview.status_code == 200, preview.text
    blank = tmp_path / "blank.pdf"
    blank.write_bytes(_blank(key))
    anchors = {a["slot_key"]: a for a in read_flat_anchors(blank, _fields(key), FlatProfile.from_layout(_SEEDS[key].layout))}
    document = pymupdf.open(stream=preview.content, filetype="pdf")
    try:
        for slot, value in {**_TYPED[key], "patient_name": "דנה כהן"}.items():
            anchor = anchors[slot]
            shown = document[anchor["page"]].get_text("text", clip=pymupdf.Rect(anchor["rect"]))
            assert _readback_matches(value, shown, contains_hebrew(value)), slot
    finally:
        document.close()

    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert signed.status_code == 200, signed.text
    assert client.get(f"/cases/{case_id}").json()["case"]["status"] == "signed"
    assert any(event["action"] == "fill_and_sign" for event in _timeline(client, case_id))


def test_a_questionnaire_may_leave_pregnancy_empty(client: TestClient, tmp_path: Path) -> None:
    _make_clinic(client)
    case_id = _open(client, QUESTIONNAIRE)
    assert client.post(f"/cases/{case_id}/load-default-form").status_code == 200
    assert _drop(client, case_id, [("id.pdf", _pdf(tmp_path / "id.pdf", _ID_LINES))]).status_code == 200
    body: dict = {}
    for slot, value in _TYPED[QUESTIONNAIRE].items():
        body = _set(client, case_id, slot, value)
    assert "pregnancy" not in body["field_values"] or not body["field_values"]["pregnancy"]
    assert body["ready_to_sign"] is True, body["signing_blockers"]
