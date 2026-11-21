"""The office's contact details: set by an owner, shown to the client on the signing and upload pages."""

from pathlib import Path

from fastapi.testclient import TestClient

from tests.support import SignedOut
from tests.test_portal import _auth, _ready, _token, client  # noqa: F401  (client is the fixture)


def _set(client: TestClient, **body):
    return client.put("/organization/contact", json=body)


def test_an_owner_sets_the_contact_and_clients_see_it(client: TestClient, tmp_path: Path) -> None:
    saved = _set(client, phone="03-1234567", email="Office@Example.co.il")
    assert saved.status_code == 200, saved.text
    assert saved.json()["contact_phone"] == "03-1234567"
    assert saved.json()["contact_email"] == "office@example.co.il"

    case_id, _documents = _ready(client, tmp_path)
    link = client.post(f"/cases/{case_id}/signing-links")
    assert link.status_code == 201, link.text
    with SignedOut(client) as anonymous:
        view = anonymous.get("/portal", headers=_auth(_token(link.json()["url"])))
    assert view.status_code == 200, view.text
    assert view.json()["office"] == {"name": "Test office", "phone": "03-1234567", "email": "office@example.co.il"}


def test_the_upload_page_names_the_office(client: TestClient) -> None:
    _set(client, phone="+972 3 1234567")
    created = client.post("/cases", json={"name": "טופס 101", "process_key": "employee_onboarding", "client_name": "דנה"})
    assert created.status_code == 201, created.text
    link = client.post(f"/cases/{created.json()['id']}/intake-link")
    assert link.status_code == 201, link.text
    token = link.json()["token"]
    with SignedOut(client) as anonymous:
        status = anonymous.get(f"/intake/{token}")
    assert status.status_code == 200, status.text
    assert status.json()["office"] == {"name": "Test office", "phone": "+972 3 1234567", "email": None}


def test_blank_values_remove_the_contact(client: TestClient) -> None:
    _set(client, phone="03-1234567", email="office@example.co.il")
    cleared = _set(client, phone="  ", email="")
    assert cleared.json()["contact_phone"] is None and cleared.json()["contact_email"] is None


def test_bad_values_are_refused_in_hebrew(client: TestClient) -> None:
    phone = _set(client, phone="call me")
    assert phone.status_code == 400 and phone.json()["code"] == "bad_phone"
    assert "טלפון" in phone.json()["detail"]
    assert _set(client, phone="12").json()["code"] == "bad_phone"
    assert _set(client, email="not-an-email").json()["code"] == "bad_email"


def test_staff_cannot_change_the_contact(client: TestClient) -> None:
    from tests.support import authenticate

    staff = authenticate(client, email="clerk@example.com", role="staff", set_header=False)
    refused = client.put("/organization/contact", json={"phone": "03-1234567"}, headers=_auth(staff["token"]))
    assert refused.status_code == 403
