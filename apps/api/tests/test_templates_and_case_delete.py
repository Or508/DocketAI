"""The form catalog, and deleting a case that was never signed."""

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

from fastapi.testclient import TestClient

from app.core.config import get_settings
from tests.support import SignedOut, authenticate
from tests.test_bl6101_sanity_drill import _auth, _bl_form, _open, _ready, _sign_body, _sources, _token

_BL_TITLE = "בל/6101 – דיווח רב-שנתי לביטוח לאומי"
_BL_SLOTS = [
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


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("BL_6101_TEMPLATE_PATH", str(tmp_path / "server" / "official.pdf"))
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


def _other_office(client: TestClient) -> dict[str, str]:
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    return {"Authorization": f"Bearer {other['token']}"}


def _templates(client: TestClient, headers: dict[str, str] | None = None) -> dict[str, dict]:
    response = client.get("/templates", headers=headers)
    assert response.status_code == 200, response.text
    return {item["process_type"]: item for item in response.json()}


def _stored(tmp_path: Path, case_id: str) -> list[Path]:
    return [path for path in (tmp_path / "storage").rglob("*") if path.is_file() and case_id in path.as_posix()]


def _rows(tmp_path: Path, case_id: str) -> dict[str, int]:
    wanted = case_id.replace("-", "")
    connection = sqlite3.connect(tmp_path / "test.db")
    try:
        counts = {}
        for table, column in (
            ("cases", "id"),
            ("documents", "case_id"),
            ("audit_logs", "case_id"),
            ("signing_links", "case_id"),
        ):
            found = connection.execute(f"SELECT {column} FROM {table}").fetchall()
            counts[table] = sum(1 for (value,) in found if str(value).replace("-", "") == wanted)
        return counts
    finally:
        connection.close()


# Catalog


def test_the_catalog_describes_bl_6101_with_its_drawers_and_ten_fields(client: TestClient, tmp_path: Path) -> None:
    catalog = _templates(client)
    assert list(catalog)[0] == "bl_6101"
    assert {"bl_6101", "onboarding", "real_estate"} <= set(catalog)
    form = catalog["bl_6101"]
    assert set(form) == {
        "process_type",
        "title_he",
        "description_he",
        "form_source",
        "default_template_available",
        "required_drawers",
        "mapped_fields",
        "case_counts",
    }
    assert form["title_he"] == _BL_TITLE
    assert form["description_he"]
    assert form["form_source"] == "official_blank"
    # No blank on the server yet.
    assert form["default_template_available"] is False

    drawers = form["required_drawers"]
    assert [item["id"] for item in drawers] == ["id_copy", "proof_of_address", "bank_confirmation"]
    assert all(item["required"] for item in drawers)
    assert [item["accepted_document_types"] for item in drawers] == [
        ["id_copy"],
        ["proof_of_address"],
        ["bank_confirmation"],
    ]
    assert drawers[0]["label_he"] == "צילום תעודת זהות"
    assert drawers[0]["reads_fields"] == ["national_id", "first_name", "last_name"]
    assert drawers[1]["reads_fields"] == ["city", "street", "house_number"]
    assert drawers[2]["reads_fields"] == ["bank_name", "bank_branch", "bank_account"]

    fields = form["mapped_fields"]
    assert [item["key"] for item in fields] == _BL_SLOTS
    by_key = {item["key"]: item for item in fields}
    assert by_key["national_id"]["label_he"] == "מספר זהות"
    assert by_key["national_id"]["field_type"] == "id_number"
    assert by_key["house_number"]["required"] is False
    assert by_key["national_id"]["sources"] == [{"drawer_id": "id_copy", "label_he": "תעודת זהות"}]
    assert by_key["street"]["sources"] == [{"drawer_id": "proof_of_address", "label_he": "חשבון ארנונה"}]
    assert by_key["bank_account"]["sources"] == [{"drawer_id": "bank_confirmation", "label_he": "אישור בנק"}]
    # Nothing reads a phone number: a person types it.
    assert by_key["phone"]["sources"] == []
    assert by_key["bank_name"]["target"]["section_he"] == "פרטי חשבון הבנק של המבוטח"
    # Without the blank there is nothing to locate the fields on.
    assert all(item["target"]["page"] is None and item["target"]["mode"] is None for item in fields)

    assert form["case_counts"] == {"total": 0, "filling": 0, "signed": 0}


def test_the_catalog_reads_field_targets_from_the_blank_once_it_is_on_the_server(
    client: TestClient, tmp_path: Path
) -> None:
    server = tmp_path / "server" / "official.pdf"
    server.parent.mkdir(parents=True, exist_ok=True)
    _bl_form(server)
    form = _templates(client)["bl_6101"]
    assert form["default_template_available"] is True
    targets = {item["key"]: item["target"] for item in form["mapped_fields"]}
    # The test form draws a plain cell for every slot, all on its first page.
    assert set(targets) == set(_BL_SLOTS)
    assert {(target["page"], target["mode"]) for target in targets.values()} == {(1, "text")}

    # A generated form is always present and is filled as plain text on its one page.
    generated = _templates(client)["real_estate"]
    assert generated["form_source"] == "generated"
    assert generated["default_template_available"] is True
    assert {(item["target"]["page"], item["target"]["mode"]) for item in generated["mapped_fields"]} == {(1, "text")}

    # Onboarding starts from the Form 101 blank this server draws.
    onboarding = _templates(client)["onboarding"]
    assert onboarding["form_source"] == "official_blank"
    assert onboarding["default_template_available"] is True
    assert [item["id"] for item in onboarding["required_drawers"] if not item["required"]] == [
        "proof_of_address",
        "pension_form",
    ]
    # Reading is switched off for that process, so no drawer is offered as a source.
    assert all(item["sources"] == [] for item in onboarding["mapped_fields"])


def test_the_official_blank_puts_the_id_number_in_digit_boxes() -> None:
    from app.core.config import REPO_ROOT
    from app.services.template_catalog import _blank_targets

    official = REPO_ROOT / "test_files_for_browser" / "bl_6101_official.pdf"
    if not official.is_file():
        pytest.skip("The official blank is not in this checkout.")
    targets = _blank_targets(str(official), (0, 0), "bl_6101")
    assert set(targets) == set(_BL_SLOTS)
    assert targets["national_id"] == (1, "digit_boxes")
    assert targets["first_name"] == (1, "text")


def test_case_counts_follow_the_callers_own_office(client: TestClient, tmp_path: Path) -> None:
    signed_case, _ = _ready(client, tmp_path)
    assert client.post(f"/cases/{signed_case}/fill-and-sign", json=_sign_body()).status_code == 200
    _open(client)
    _open(client)
    client.post("/cases", json={"name": "Hire", "process_key": "onboarding"})

    catalog = _templates(client)
    assert catalog["bl_6101"]["case_counts"] == {"total": 3, "filling": 2, "signed": 1}
    assert catalog["onboarding"]["case_counts"] == {"total": 1, "filling": 1, "signed": 0}
    assert catalog["real_estate"]["case_counts"] == {"total": 0, "filling": 0, "signed": 0}

    headers = _other_office(client)
    theirs = _templates(client, headers)
    assert all(item["case_counts"] == {"total": 0, "filling": 0, "signed": 0} for item in theirs.values())
    client.post("/cases", headers=headers, json={"name": "Theirs", "process_key": "bl_6101"})
    assert _templates(client, headers)["bl_6101"]["case_counts"] == {"total": 1, "filling": 1, "signed": 0}
    assert _templates(client)["bl_6101"]["case_counts"]["total"] == 3

    with SignedOut(client) as anonymous:
        assert anonymous.get("/templates").status_code == 401


# Delete


def test_deleting_a_draft_case_removes_its_files_rows_and_links(client: TestClient, tmp_path: Path) -> None:
    case_id, _form_id = _ready(client, tmp_path)
    keep = _open(client)
    _sources(client, keep, tmp_path)
    token = _token(client, case_id)
    assert client.get("/portal", headers=_auth(token)).status_code == 200
    assert len(_stored(tmp_path, case_id)) == 4
    before = _rows(tmp_path, case_id)
    assert before["cases"] == 1 and before["documents"] == 4 and before["signing_links"] == 1
    assert before["audit_logs"] > 0

    deleted = client.delete(f"/cases/{case_id}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""

    assert client.get(f"/cases/{case_id}").status_code == 404
    assert client.get(f"/cases/{case_id}/timeline").status_code == 404
    assert case_id not in {item["id"] for item in client.get("/cases").json()}
    assert client.get("/portal", headers=_auth(token)).status_code == 404
    assert _stored(tmp_path, case_id) == []
    assert _rows(tmp_path, case_id) == {"cases": 0, "documents": 0, "audit_logs": 0, "signing_links": 0}
    # A second delete finds nothing.
    assert client.delete(f"/cases/{case_id}").status_code == 404

    # The other case of the same office is untouched.
    assert client.get(f"/cases/{keep}").status_code == 200
    assert len(_stored(tmp_path, keep)) == 3
    assert _rows(tmp_path, keep)["documents"] == 3
    assert _templates(client)["bl_6101"]["case_counts"] == {"total": 1, "filling": 1, "signed": 0}


def test_an_empty_case_can_be_deleted(client: TestClient, tmp_path: Path) -> None:
    case_id = _open(client)
    assert client.delete(f"/cases/{case_id}").status_code == 204
    assert client.get(f"/cases/{case_id}").status_code == 404
    assert _rows(tmp_path, case_id)["cases"] == 0


def test_a_signed_case_cannot_be_deleted_until_it_is_reopened(client: TestClient, tmp_path: Path) -> None:
    case_id, _form_id = _ready(client, tmp_path)
    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body())
    assert signed.status_code == 200, signed.text
    code = signed.json()["case"]["audit"]["signer_verification_id"]
    stored = sorted(_stored(tmp_path, case_id))
    rows = _rows(tmp_path, case_id)

    refused = client.delete(f"/cases/{case_id}")
    assert refused.status_code == 409, refused.text
    assert "Reopen" in refused.json()["detail"]
    # Nothing moved: the case, its packet and its seal are all still there.
    assert client.get(f"/cases/{case_id}").json()["case"]["status"] == "signed"
    assert client.get(f"/cases/{case_id}/signed-document").status_code == 200
    assert sorted(_stored(tmp_path, case_id)) == stored
    assert _rows(tmp_path, case_id) == rows
    assert client.get(f"/verify/{code}").json()["valid"] is True

    # Reopened, it is a draft again and may go, along with the superseded packet.
    assert client.post(f"/cases/{case_id}/reopen").status_code == 200
    assert any("/signed/" in path.as_posix() for path in _stored(tmp_path, case_id))
    assert client.delete(f"/cases/{case_id}").status_code == 204
    assert _stored(tmp_path, case_id) == []
    assert _rows(tmp_path, case_id) == {"cases": 0, "documents": 0, "audit_logs": 0, "signing_links": 0}
    assert client.get(f"/verify/{code}").status_code == 404


def test_another_organization_cannot_delete_a_case(client: TestClient, tmp_path: Path) -> None:
    case_id, _form_id = _ready(client, tmp_path)
    stored = sorted(_stored(tmp_path, case_id))
    rows = _rows(tmp_path, case_id)
    headers = _other_office(client)

    hidden = client.delete(f"/cases/{case_id}", headers=headers)
    assert hidden.status_code == 404, hidden.text
    assert hidden.json() == client.delete("/cases/00000000-0000-0000-0000-000000000000").json()
    with SignedOut(client) as anonymous:
        assert anonymous.delete(f"/cases/{case_id}").status_code == 401

    assert client.get(f"/cases/{case_id}").status_code == 200
    assert sorted(_stored(tmp_path, case_id)) == stored
    assert _rows(tmp_path, case_id) == rows

    # Their own draft is theirs to delete.
    own = client.post("/cases", headers=headers, json={"name": "Theirs", "process_key": "bl_6101"}).json()["id"]
    assert client.delete(f"/cases/{own}", headers=headers).status_code == 204
    assert client.get(f"/cases/{case_id}").status_code == 200
