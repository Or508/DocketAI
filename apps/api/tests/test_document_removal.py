"""A wrong file can be taken out of a drawer, and what it supplied goes with it."""

from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

from fastapi.testclient import TestClient

from tests.test_upload_drawers import _open, _pdf, _picture, _upload, client  # noqa: F401

_DANA = ["השם הפרטי", "דנה", "שם המשפחה", "כהן", "1 0000000 9"]
_NOA = ["השם הפרטי", "נועה", "שם המשפחה", "לוי", "2 0000000 8"]
_DANA_VALUES = {"first_name": "דנה", "last_name": "כהן", "national_id": "100000009"}
_NOA_VALUES = {"first_name": "נועה", "last_name": "לוי", "national_id": "200000008"}


def _card(client: TestClient, case_id: str, name: str, lines: list[str], drawer: str = "id_copy", **extra: str):
    uploaded = _upload(client, case_id, name, _pdf(lines), "application/pdf", document_type=drawer, **extra)
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()


def _workspace(client: TestClient, case_id: str) -> dict:
    return client.get(f"/cases/{case_id}").json()


def _drawers(workspace: dict) -> dict[str, str]:
    return {item["filename"]: item["document_type"] for item in workspace["gap"]["identified"]}


def _document_id(workspace: dict, name: str) -> str:
    return next(item["document_id"] for item in workspace["gap"]["identified"] if item["filename"] == name)


def _stored_files(tmp_path: Path) -> int:
    return sum(1 for item in (tmp_path / "storage").rglob("*") if item.is_file())


def _office_sets(client: TestClient, case_id: str, key: str, value: str) -> None:
    saved = client.post(f"/cases/{case_id}/fields", json={"key": key, "value": value})
    assert saved.status_code == 200, saved.text


def test_removing_the_wrong_file_lets_the_right_one_supply_the_details(
    client: TestClient, tmp_path: Path  # noqa: F811
) -> None:
    case_id = _open(client)
    _card(client, case_id, "wrong.pdf", _DANA)
    _office_sets(client, case_id, "city", "חיפה")
    _card(client, case_id, "right.pdf", _NOA)
    before = _workspace(client, case_id)
    # The second card names another person, so it supplied nothing.
    assert {key: before["field_values"][key] for key in _DANA_VALUES} == _DANA_VALUES
    files = _stored_files(tmp_path)

    removed = client.delete(f"/cases/{case_id}/documents/{_document_id(before, 'wrong.pdf')}")
    assert removed.status_code == 200, removed.text
    after = removed.json()
    assert _drawers(after) == {"right.pdf": "id_copy"}
    assert after["field_values"] == {**_NOA_VALUES, "city": "חיפה"}
    sources = after["field_sources"]
    assert sources["city"]["source"] == "office"
    right_id = _document_id(after, "right.pdf")
    assert {sources[key]["document_id"] for key in _NOA_VALUES} == {right_id}
    assert _stored_files(tmp_path) == files - 1
    assert after["case"]["document_count"] == 1
    assert _workspace(client, case_id)["field_values"] == after["field_values"]


def test_a_detail_the_office_corrected_survives_the_removal(client: TestClient) -> None:  # noqa: F811
    case_id = _open(client)
    _card(client, case_id, "card.pdf", _DANA)
    _office_sets(client, case_id, "first_name", "דניאלה")
    workspace = _workspace(client, case_id)
    removed = client.delete(f"/cases/{case_id}/documents/{_document_id(workspace, 'card.pdf')}")
    assert removed.status_code == 200, removed.text
    body = removed.json()
    assert body["field_values"] == {"first_name": "דניאלה"}
    assert body["gap"]["identified"] == []
    assert "id_copy" in {item["type_key"] for item in body["gap"]["missing"]}
    assert body["case"]["status"] == "draft"


def test_removing_a_file_that_is_not_there_is_a_404(client: TestClient) -> None:  # noqa: F811
    case_id = _open(client)
    other = _open(client)
    _card(client, other, "card.pdf", _DANA)
    foreign = _document_id(_workspace(client, other), "card.pdf")
    assert client.delete(f"/cases/{case_id}/documents/{foreign}").status_code == 404
    assert _drawers(_workspace(client, other)) == {"card.pdf": "id_copy"}
    assert _workspace(client, other)["field_values"] == _DANA_VALUES


def test_replace_existing_swaps_the_file_in_the_drawer(client: TestClient, tmp_path: Path) -> None:  # noqa: F811
    case_id = _open(client)
    _card(client, case_id, "old.pdf", _DANA)
    _card(client, case_id, "bill.pdf", ["חשבון ארנונה"], drawer="proof_of_address")
    files = _stored_files(tmp_path)

    body = _card(client, case_id, "new.pdf", _NOA, replace_existing="true")
    assert body["accepted_filenames"] == ["new.pdf"]
    workspace = _workspace(client, case_id)
    assert _drawers(workspace) == {"new.pdf": "id_copy", "bill.pdf": "proof_of_address"}
    assert workspace["field_values"] == _NOA_VALUES
    assert _stored_files(tmp_path) == files

    # Without the flag the drawer keeps both, and the first one still speaks.
    _card(client, case_id, "second.pdf", _DANA)
    workspace = _workspace(client, case_id)
    assert set(_drawers(workspace)) == {"new.pdf", "second.pdf", "bill.pdf"}
    assert workspace["field_values"] == _NOA_VALUES


def test_a_refused_upload_replaces_nothing(client: TestClient) -> None:  # noqa: F811
    case_id = _open(client)
    _card(client, case_id, "old.pdf", _DANA)
    refused = _upload(
        client, case_id, "notes.png", b"not a picture", "image/png", document_type="id_copy", replace_existing="true"
    )
    assert refused.status_code == 200, refused.text
    assert [item["filename"] for item in refused.json()["rejected"]] == ["notes.png"]
    workspace = _workspace(client, case_id)
    assert _drawers(workspace) == {"old.pdf": "id_copy"}
    assert workspace["field_values"] == _DANA_VALUES


def test_moving_a_file_to_another_drawer_takes_its_details_back(client: TestClient) -> None:  # noqa: F811
    case_id = _open(client)
    _card(client, case_id, "first.pdf", _DANA)
    _office_sets(client, case_id, "city", "חיפה")
    _card(client, case_id, "second.pdf", _NOA)
    workspace = _workspace(client, case_id)
    first = _document_id(workspace, "first.pdf")

    moved = client.post(
        f"/cases/{case_id}/classify-manual",
        json={"document_id": first, "document_type": "proof_of_address"},
    )
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert _drawers(body) == {"first.pdf": "proof_of_address", "second.pdf": "id_copy"}
    # The moved card no longer speaks for identity; the one left in the drawer does.
    assert body["field_values"] == {**_NOA_VALUES, "city": "חיפה"}
    assert body["field_sources"]["city"]["source"] == "office"

    back = client.post(
        f"/cases/{case_id}/classify-manual",
        json={"document_id": first, "document_type": "id_copy"},
    )
    assert back.status_code == 200, back.text
    assert back.json()["field_values"] == {**_NOA_VALUES, "city": "חיפה"}


def test_a_picture_filed_wrongly_moves_clean(client: TestClient) -> None:  # noqa: F811
    case_id = _open(client)
    _upload(client, case_id, "arnona.jpeg", _picture("JPEG"), "image/jpeg", document_type="id_copy")
    _card(client, case_id, "card.pdf", _DANA)
    workspace = _workspace(client, case_id)
    moved = client.post(
        f"/cases/{case_id}/classify-manual",
        json={"document_id": _document_id(workspace, "arnona.jpeg"), "document_type": "proof_of_address"},
    )
    assert moved.status_code == 200, moved.text
    assert _drawers(moved.json()) == {"arnona.jpeg": "proof_of_address", "card.pdf": "id_copy"}
    assert moved.json()["field_values"] == _DANA_VALUES


def test_the_form_can_be_removed_and_unmarked(client: TestClient, tmp_path: Path) -> None:  # noqa: F811
    from tests.test_bl6101_sanity_drill import _bl_form

    case_id = _open(client)
    form = _bl_form(tmp_path / "bl.pdf").read_bytes()
    assert _upload(client, case_id, "bl.pdf", form, "application/pdf", role="form").status_code == 200
    _card(client, case_id, "card.pdf", _DANA)
    forms = client.get(f"/cases/{case_id}/intake").json()["forms"]
    form_id = forms[0]["document_id"]

    unmarked = client.put(f"/cases/{case_id}/documents/{form_id}/role", json={"role": "evidence"})
    assert unmarked.status_code == 200, unmarked.text
    assert _workspace(client, case_id)["field_values"] == _DANA_VALUES
    marked = client.put(f"/cases/{case_id}/documents/{form_id}/role", json={"role": "form"})
    assert marked.status_code == 200, marked.text

    removed = client.delete(f"/cases/{case_id}/documents/{form_id}")
    assert removed.status_code == 200, removed.text
    assert client.get(f"/cases/{case_id}/intake").json()["forms"] == []
    assert removed.json()["field_values"] == _DANA_VALUES
    assert client.get(f"/cases/{case_id}/documents/{form_id}/file").status_code == 404
