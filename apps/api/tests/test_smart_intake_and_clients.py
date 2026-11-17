"""Smart intake, the real estate form end to end, the client book, and a new case from the vault."""

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

from fastapi.testclient import TestClient

from tests.support import SignedOut, authenticate
from tests.test_bl6101_sanity_drill import _ID, _PNG_B64, _auth, _set, _sign_body, _token
from tests.test_smart_upload_and_real_estate import (  # noqa: F401  (client is the fixture)
    _DEAL_SLOTS,
    _READ,
    _assert_deal_filled,
    _deal_blank,
    _drawers,
    _drop,
    _everyday,
    _forms,
    _prepared_deal,
    _timeline,
    client,
)

_DANA = "דנה כהן"
_TYPED = {"house_number": "15", "phone": "0501234567"}
_FORM_101_SLOTS = [
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


def _new(client: TestClient, key: str, client_name: str | None, headers: dict[str, str] | None = None) -> str:
    body = {"name": "Case", "process_key": key}
    if client_name is not None:
        body["client_name"] = client_name
    created = client.post("/cases", headers=headers, json=body)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _other_office(client: TestClient) -> dict[str, str]:
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    return {"Authorization": f"Bearer {other['token']}"}


def _vault_case(client: TestClient, tmp_path: Path) -> str:
    """Dana's BL/6101 case: the three documents dropped at once and read, the rest typed."""
    case_id = _new(client, "bl_6101", _DANA)
    dropped = _drop(client, case_id, _everyday(tmp_path))
    assert dropped.status_code == 200, dropped.text
    for key, value in _TYPED.items():
        _set(client, case_id, key, value)
    return case_id


def _quick(client: TestClient, source: str, process_type: str, headers: dict[str, str] | None = None):
    return client.post(
        "/clients/quick-case", headers=headers, json={"source_case_id": source, "process_type": process_type}
    )


def _clients(client: TestClient, headers: dict[str, str] | None = None) -> list[dict]:
    response = client.get("/clients", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# Smart intake


def test_one_drop_files_the_three_documents_fills_the_fields_and_is_on_the_timeline(
    client: TestClient, tmp_path: Path
) -> None:
    case_id = _new(client, "bl_6101", _DANA)
    dropped = _drop(client, case_id, _everyday(tmp_path))
    assert dropped.status_code == 200, dropped.text
    body = dropped.json()

    # Every workspace key is at the root, so the screen can take the response as its new state.
    assert set(client.get(f"/cases/{case_id}").json()) <= set(body)
    assert body["case"]["id"] == case_id and body["case"]["document_count"] == 3
    assert _drawers(body) == {
        "id_copy": ["id.pdf"],
        "proof_of_address": ["arnona.pdf"],
        "bank_confirmation": ["bank.pdf"],
    }
    assert body["gap"]["missing"] == [] and body["gap"]["unrecognized"] == []
    for key, value in _READ.items():
        assert body["field_values"][key] == value, key
        assert body["field_sources"][key]["source"] == "document", key

    record = next(event for event in _timeline(client, case_id) if event["action"] == "smart_upload_completed")
    listed = [
        {key: item[key] for key in ("filename", "role", "document_type")} for item in record["metadata"]["routed_files"]
    ]
    assert listed == [
        {"filename": "id.pdf", "role": "evidence", "document_type": "id_copy"},
        {"filename": "arnona.pdf", "role": "evidence", "document_type": "proof_of_address"},
        {"filename": "bank.pdf", "role": "evidence", "document_type": "bank_confirmation"},
    ]

    # Another office cannot drop files here, and a stranger is turned away.
    before = client.get(f"/cases/{case_id}").json()
    assert _drop(client, case_id, _everyday(tmp_path), _other_office(client)).status_code == 404
    with SignedOut(client) as anonymous:
        assert anonymous.post(
            f"/cases/{case_id}/smart-upload", files=[("files", ("id.pdf", b"%PDF-1.4", "application/pdf"))]
        ).status_code == 401
    assert client.get(f"/cases/{case_id}").json() == before


# Real estate


def test_real_estate_loads_its_form_fills_it_and_the_buyer_signs_it(client: TestClient, tmp_path: Path) -> None:
    listed = {item["process_type"]: item for item in client.get("/templates").json()}
    for key in ("onboarding", "real_estate", "employee_onboarding"):
        assert listed[key]["default_template_available"] is True, key
    assert [item["key"] for item in listed["real_estate"]["mapped_fields"]] == _DEAL_SLOTS

    case_id, form_id, values = _prepared_deal(client, tmp_path)
    form = _forms(client, case_id)[0]
    assert (form["filename"], form["role"], form["bound"]) == ("real_estate_official.pdf", "form", len(_DEAL_SLOTS))
    assert client.get(f"/cases/{case_id}/documents/{form_id}/file").content == _deal_blank()

    preview = client.get(f"/cases/{case_id}/documents/{form_id}/filled-preview")
    assert preview.status_code == 200, preview.text
    _assert_deal_filled(preview.content, values, tmp_path).close()

    token = _token(client, case_id)
    view = client.get("/portal", headers=_auth(token)).json()
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG_B64, "review_digest": view["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    office = client.get(f"/cases/{case_id}").json()
    assert office["case"]["status"] == "signed"
    packet = client.get(f"/cases/{case_id}/signed-document").content
    assert hashlib.sha256(packet).hexdigest() == office["case"]["audit"]["file_sha256"]
    document = _assert_deal_filled(packet, values, tmp_path)
    try:
        # The two form pages with the signature on the declaration page, then the seal page.
        assert document.page_count == 3
        assert document[1].get_image_info() != [] and document[0].get_image_info() == []
    finally:
        document.close()

    # A signed case takes no more files, and another office reaches nothing of it.
    assert _drop(client, case_id, _everyday(tmp_path)).status_code == 409
    assert client.get(f"/cases/{case_id}").json()["case"]["status"] == "signed"
    headers = _other_office(client)
    assert client.post(f"/cases/{case_id}/load-default-form", headers=headers).status_code == 404
    assert client.get(f"/cases/{case_id}/signed-document", headers=headers).status_code == 404


# The client book


def test_the_client_book_gathers_cases_by_id_number_and_by_name(client: TestClient, tmp_path: Path) -> None:
    assert _clients(client) == []

    vault = _vault_case(client, tmp_path)
    # No ID number on this one yet: it joins Dana by her name.
    hire = _new(client, "onboarding", "  דנה   כהן ")
    deal, _form_id, _values = _prepared_deal(client, tmp_path)
    assert client.post(f"/cases/{deal}/fill-and-sign", json=_sign_body()).status_code == 200
    yossi = _new(client, "real_estate", "יוסי לוי")
    _new(client, "onboarding", None)

    book = _clients(client)
    assert [item["client_key"] for item in book] == ["name:יוסי לוי", f"id:{_ID}"]

    dana = book[1]
    assert dana["client_name"] == _DANA
    assert dana["id_number"] == _ID
    assert dana["phone"] == "0501234567"
    assert dana["address_summary"] == "הרצל 15, תל אביב"
    # The account number is never listed in full.
    assert dana["bank_summary"] == "לאומי · סניף 800 · חשבון ••6789"
    assert "456789" not in str(book)
    assert (dana["total_cases"], dana["signed_cases"]) == (3, 1)
    assert dana["reusable_docs_count"] == 3
    assert dana["reusable_doc_types"] == ["id_copy", "proof_of_address", "bank_confirmation"]
    assert dana["latest_case_id"] == deal
    assert [item["case_id"] for item in dana["cases"]] == [deal, hire, vault]
    assert [item["process_type"] for item in dana["cases"]] == ["real_estate", "onboarding", "bl_6101"]
    seal = client.get(f"/cases/{deal}").json()["case"]["audit"]
    signed = dana["cases"][0]
    assert set(signed) == {"case_id", "process_type", "status", "created_at", "signed_at", "verification_id"}
    assert signed["status"] == "signed" and signed["signed_at"]
    assert signed["verification_id"] == seal["signer_verification_id"]
    assert all(item["verification_id"] is None and item["signed_at"] is None for item in dana["cases"][1:])

    other = book[0]
    assert (other["client_name"], other["id_number"], other["phone"]) == ("יוסי לוי", None, None)
    assert (other["total_cases"], other["signed_cases"], other["reusable_docs_count"]) == (1, 0, 0)
    assert other["latest_case_id"] == yossi
    assert other["address_summary"] is None and other["bank_summary"] is None

    # Another office has its own book, and a stranger has none.
    headers = _other_office(client)
    assert _clients(client, headers) == []
    theirs = _new(client, "onboarding", _DANA, headers)
    assert [item["latest_case_id"] for item in _clients(client, headers)] == [theirs]
    assert [item["total_cases"] for item in _clients(client)] == [1, 3]
    with SignedOut(client) as anonymous:
        assert anonymous.get("/clients").status_code == 401


# A new case from the vault


def test_a_quick_case_copies_the_vault_loads_the_form_and_arrives_filled(client: TestClient, tmp_path: Path) -> None:
    source = _vault_case(client, tmp_path)
    before = client.get(f"/cases/{source}").json()

    opened = _quick(client, source, "employee_onboarding")
    assert opened.status_code == 201, opened.text
    body = opened.json()
    case_id = body["case"]["id"]
    assert case_id != source
    assert body["case"]["client_name"] == _DANA
    assert body["process"]["key"] == "employee_onboarding"
    # The three documents and the blank Form 101.
    assert body["case"]["document_count"] == 4
    assert _drawers(body) == {
        "id_copy": ["id.pdf"],
        "proof_of_address": ["arnona.pdf"],
        "bank_confirmation": ["bank.pdf"],
    }
    forms = _forms(client, case_id)
    assert [(item["filename"], item["role"], item["bound"]) for item in forms] == [("form_101_official.pdf", "form", 10)]

    # Every slot is filled before anyone touches the case: read from the copies, or carried over.
    assert body["field_values"] == {**_READ, **_TYPED}
    assert sorted(body["field_values"]) == sorted(_FORM_101_SLOTS)
    assert body["missing_fields"] == []
    assert all(body["field_sources"][key]["source"] == "document" for key in _READ)
    assert all(body["field_sources"][key]["source"] == "office" for key in _TYPED)
    assert body["ready_to_sign"] is True, body["signing_blockers"]
    # The copies are this case's own files: its values point at them, not at the source case.
    own = {item["document_id"] for item in body["gap"]["identified"]}
    assert {body["field_sources"][key]["document_id"] for key in _READ} <= own
    assert own.isdisjoint({item["document_id"] for item in before["gap"]["identified"]})

    events = _timeline(client, case_id)
    actions = [event["action"] for event in events]
    assert "default_form_loaded" in actions
    record = next(event for event in events if event["action"] == "client_vault_reused")
    staff = client.get("/auth/me").json()
    assert record["actor"] == f"user:{staff['id']}"
    assert record["metadata"]["source_case_id"] == source
    assert record["metadata"]["documents"] == 3
    assert record["metadata"]["document_types"] == ["id_copy", "proof_of_address", "bank_confirmation"]
    assert sorted(record["metadata"]["fields"]) == sorted(_TYPED)
    assert record["metadata"]["form_loaded"] is True

    # The source case is exactly as it was, and the new case can be signed as it stands.
    assert client.get(f"/cases/{source}").json() == before
    assert client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body()).status_code == 200
    dana = _clients(client)[0]
    assert (dana["total_cases"], dana["signed_cases"], dana["latest_case_id"]) == (2, 1, case_id)


def test_a_quick_case_takes_only_what_the_new_process_has_a_place_for(client: TestClient, tmp_path: Path) -> None:
    source = _vault_case(client, tmp_path)

    # Real estate keeps an ID copy only; the buyer's name comes from the client. The office's other name for it works.
    deal = _quick(client, source, "real_estate_closing")
    assert deal.status_code == 201, deal.text
    body = deal.json()
    assert body["process"]["key"] == "real_estate"
    assert _drawers(body) == {"id_copy": ["id.pdf"]}
    assert body["case"]["document_count"] == 2
    assert [item["filename"] for item in _forms(client, body["case"]["id"])] == ["real_estate_official.pdf"]
    assert body["field_values"] == {"buyer_name": _DANA}
    record = next(e for e in _timeline(client, body["case"]["id"]) if e["action"] == "client_vault_reused")
    assert record["metadata"]["document_types"] == ["id_copy"] and record["metadata"]["fields"] == ["buyer_name"]

    # Onboarding reads no documents, so its personal details are all carried from the client.
    hire = _quick(client, body["case"]["id"], "onboarding")
    assert hire.status_code == 201, hire.text
    onboarding = hire.json()
    assert sorted(_drawers(onboarding)) == ["bank_confirmation", "id_copy", "proof_of_address"]
    assert onboarding["field_values"] == {
        "full_name": _DANA,
        "national_id": _ID,
        "phone": "0501234567",
        "address_he": "הרצל 15, תל אביב",
    }
    assert sorted(item["key"] for item in onboarding["missing_fields"]) == ["email", "start_date"]

    # BL/6101 has no blank on this server: the case still opens, filled from the copies, and says so.
    insured = _quick(client, source, "bl_6101")
    assert insured.status_code == 201, insured.text
    assert insured.json()["case"]["document_count"] == 3
    assert _forms(client, insured.json()["case"]["id"]) == []
    for key, value in {**_READ, **_TYPED}.items():
        assert insured.json()["field_values"][key] == value, key
    record = next(e for e in _timeline(client, insured.json()["case"]["id"]) if e["action"] == "client_vault_reused")
    assert record["metadata"]["form_loaded"] is False


def test_a_quick_case_is_refused_for_unknown_processes_other_offices_and_strangers(
    client: TestClient, tmp_path: Path
) -> None:
    source = _vault_case(client, tmp_path)
    count = len(client.get("/cases").json())

    assert _quick(client, source, "no_such_process").status_code == 404
    assert _quick(client, "00000000-0000-0000-0000-000000000000", "onboarding").status_code == 404
    assert _quick(client, "not-a-case", "onboarding").status_code == 422
    assert client.post("/clients/quick-case", json={"source_case_id": source}).status_code == 422

    # Another office cannot open a case from this one, and nothing is created for them.
    headers = _other_office(client)
    assert _quick(client, source, "employee_onboarding", headers).status_code == 404
    assert client.get("/cases", headers=headers).json() == []
    assert _clients(client, headers) == []
    with SignedOut(client) as anonymous:
        assert anonymous.post(
            "/clients/quick-case", json={"source_case_id": source, "process_type": "onboarding"}
        ).status_code == 401
    assert len(client.get("/cases").json()) == count
