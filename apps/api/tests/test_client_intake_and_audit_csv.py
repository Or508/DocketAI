"""The client's own document intake link, and the audit trail as a CSV file."""

import csv
import io
import json
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("PIL")

from fastapi.testclient import TestClient

from tests.support import SignedOut, authenticate
from tests.test_bl6101_sanity_drill import _ID, _pdf, _set, _sign_body
from tests.test_smart_upload_and_real_estate import (  # noqa: F401  (client is the fixture)
    _BANK_LINES,
    _READ,
    _drop,
    _everyday,
    _timeline,
    client,
)

_DANA = "דנה כהן"
_CLIENT_ACTOR = "לקוח (העלאה עצמית)"
_LABELS = {
    "id_copy": "תעודת זהות",
    "proof_of_address": "אישור כתובת / ארנונה",
    "bank_confirmation": "אישור ניהול חשבון בנק",
}
_STATUS_KEYS = {
    "case_id",
    "client_name",
    "process_type",
    "process_title_he",
    "status",
    "required_drawers",
    "all_drawers_filled",
}
_DRAWER_KEYS = {"document_type", "label_he", "filled", "filename"}
_CSV_COLUMNS = ["event_id", "created_at", "case_id", "client_name", "process_type", "action", "actor"]
# What the documents say about the client, apart from the name the page greets them by.
# The bank's name is left out: it is also a word in the title of the National Insurance form.
_PRIVATE = [value for key, value in _READ.items() if key not in {"first_name", "last_name", "bank_name"}]
_TYPED = {"house_number": "15", "phone": "0501234567"}


def _new(client: TestClient, key: str = "bl_6101", client_name: str = _DANA, headers: dict[str, str] | None = None) -> str:
    created = client.post("/cases", headers=headers, json={"name": "Case", "process_key": key, "client_name": client_name})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _other_office(client: TestClient) -> dict[str, str]:
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    return {"Authorization": f"Bearer {other['token']}"}


def _link(client: TestClient, case_id: str, headers: dict[str, str] | None = None) -> dict:
    created = client.post(f"/cases/{case_id}/intake-link", headers=headers)
    assert created.status_code == 201, created.text
    return created.json()


def _send(client: TestClient, token: str, files: list[tuple[str, bytes]], field: str = "files", **data: str):
    """The client's upload: no office session goes with it."""
    with SignedOut(client) as anonymous:
        return anonymous.post(
            f"/intake/{token}/upload",
            files=[(field, (name, content, "application/pdf")) for name, content in files],
            data=data or None,
        )


def _status(client: TestClient, token: str):
    with SignedOut(client) as anonymous:
        return anonymous.get(f"/intake/{token}")


def _assert_public(body: dict, extra: set[str] = frozenset()) -> None:
    """Only the agreed keys, and nothing a document says about the client."""
    assert set(body) == _STATUS_KEYS | set(extra)
    for drawer in body["required_drawers"]:
        assert set(drawer) == _DRAWER_KEYS
    for item in body.get("routed_files", []):
        assert set(item) == {"filename", "outcome", "document_type", "label_he", "reason_he"}
    # The case id is random hex and could hold a short run of digits by chance.
    text = json.dumps({key: value for key, value in body.items() if key != "case_id"}, ensure_ascii=False)
    for value in _PRIVATE:
        assert value not in text, value


def _csv(client: TestClient, headers: dict[str, str] | None = None, **params) -> list[dict[str, str]]:
    response = client.get("/audit/export.csv", headers=headers, params=params)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"].startswith('attachment; filename="audit-log-')
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"\xef\xbb\xbf")
    text = response.content.decode("utf-8")
    assert text[0] == "﻿" and text[1:].startswith(",".join(_CSV_COLUMNS) + "\r\n")
    rows = list(csv.reader(io.StringIO(text[1:], newline="")))
    assert rows[0] == _CSV_COLUMNS
    assert all(len(row) == len(_CSV_COLUMNS) for row in rows)
    return [dict(zip(_CSV_COLUMNS, row, strict=True)) for row in rows[1:]]


# The office opens the link


def test_the_office_opens_an_intake_link_and_a_new_one_replaces_it(client: TestClient) -> None:
    case_id = _new(client)
    first = _link(client, case_id)
    assert set(first) == {"case_id", "token", "url_path", "expires_at"}
    assert first["case_id"] == case_id
    assert len(first["token"]) >= 32 and first["url_path"] == f"/upload/{first['token']}"
    assert first["expires_at"] is not None

    opened = _status(client, first["token"])
    assert opened.status_code == 200, opened.text
    assert opened.json()["case_id"] == case_id

    record = next(event for event in _timeline(client, case_id) if event["action"] == "intake_link_created")
    staff = client.get("/auth/me").json()
    assert record["actor"] == f"user:{staff['id']}"
    assert record["metadata"]["link_id"] and record["metadata"]["expires_at"]
    # The token is shown once. Nothing the office can read later carries it.
    assert first["token"] not in client.get(f"/cases/{case_id}/timeline").text
    assert first["token"] not in client.get(f"/cases/{case_id}").text
    assert first["token"] not in client.get("/audit").text

    # A second link is a new token, and the first one stops working.
    second = _link(client, case_id)
    assert second["token"] != first["token"]
    assert _status(client, first["token"]).status_code == 410
    assert _status(client, second["token"]).status_code == 200
    created = [event for event in _timeline(client, case_id) if event["action"] == "intake_link_created"]
    assert len(created) == 2

    # Opening a link changes nothing on the case.
    assert client.get(f"/cases/{case_id}").json()["case"]["document_count"] == 0


def test_another_office_and_a_stranger_cannot_open_a_link(client: TestClient) -> None:
    case_id = _new(client)
    headers = _other_office(client)
    assert client.post(f"/cases/{case_id}/intake-link", headers=headers).status_code == 404
    with SignedOut(client) as anonymous:
        assert anonymous.post(f"/cases/{case_id}/intake-link").status_code == 401
    assert [event for event in _timeline(client, case_id) if event["action"] == "intake_link_created"] == []

    # A link opens its own case only, whoever holds it: the other office's session adds nothing.
    token = _link(client, case_id)["token"]
    theirs = _link(client, _new(client, client_name="רון לוי", headers=headers), headers=headers)["token"]
    assert client.get(f"/intake/{token}", headers=headers).json()["case_id"] == case_id
    assert _status(client, theirs).json()["client_name"] == "רון לוי"


# The public page


def test_the_public_status_names_the_drawers_and_leaks_no_personal_values(client: TestClient, tmp_path: Path) -> None:
    case_id = _new(client)
    token = _link(client, case_id)["token"]

    empty = _status(client, token)
    assert empty.status_code == 200, empty.text
    body = empty.json()
    _assert_public(body)
    assert body["case_id"] == case_id and body["client_name"] == _DANA
    assert body["process_type"] == "bl_6101" and body["process_title_he"]
    assert body["status"] != "signed" and body["all_drawers_filled"] is False
    assert [(item["document_type"], item["label_he"]) for item in body["required_drawers"]] == list(_LABELS.items())
    assert all(item["filled"] is False and item["filename"] is None for item in body["required_drawers"])

    # The office reads the client's documents into the case. The link still shows only what arrived.
    assert _drop(client, case_id, _everyday(tmp_path)).status_code == 200
    workspace = client.get(f"/cases/{case_id}").json()
    assert workspace["field_values"]["national_id"] == _ID
    full = _status(client, token).json()
    _assert_public(full)
    assert full["all_drawers_filled"] is True
    assert {item["document_type"]: item["filename"] for item in full["required_drawers"]} == {
        "id_copy": "id.pdf",
        "proof_of_address": "arnona.pdf",
        "bank_confirmation": "bank.pdf",
    }
    assert all(item["filled"] for item in full["required_drawers"])

    # A token nobody issued, of any shape, is not found, for reading and for sending.
    for unknown in ("x" * 43, "short", "bad token!"):
        assert _status(client, unknown).status_code == 404
        assert _send(client, unknown, [("id.pdf", b"%PDF-1.4")]).status_code == 404


def test_a_client_upload_is_sorted_read_and_recorded(client: TestClient, tmp_path: Path) -> None:
    case_id = _new(client)
    token = _link(client, case_id)["token"]

    sent = _send(client, token, _everyday(tmp_path))
    assert sent.status_code == 200, sent.text
    body = sent.json()
    _assert_public(body, {"routed_files"})
    assert body["all_drawers_filled"] is True
    assert [(item["filename"], item["outcome"], item["document_type"], item["label_he"]) for item in body["routed_files"]] == [
        ("id.pdf", "received", "id_copy", _LABELS["id_copy"]),
        ("arnona.pdf", "received", "proof_of_address", _LABELS["proof_of_address"]),
        ("bank.pdf", "received", "bank_confirmation", _LABELS["bank_confirmation"]),
    ]
    assert {item["document_type"]: (item["filled"], item["filename"]) for item in body["required_drawers"]} == {
        "id_copy": (True, "id.pdf"),
        "proof_of_address": (True, "arnona.pdf"),
        "bank_confirmation": (True, "bank.pdf"),
    }
    assert _status(client, token).json() == {key: value for key, value in body.items() if key != "routed_files"}

    # The office sees the same work a smart upload does: drawers filled and every detail read.
    workspace = client.get(f"/cases/{case_id}").json()
    assert workspace["case"]["document_count"] == 3
    assert workspace["gap"]["missing"] == [] and workspace["gap"]["unrecognized"] == []
    for key, value in _READ.items():
        assert workspace["field_values"][key] == value, key
        assert workspace["field_sources"][key]["source"] == "document", key

    timeline = _timeline(client, case_id)
    record = next(event for event in timeline if event["action"] == "client_intake_uploaded")
    assert record["actor"] == _CLIENT_ACTOR
    assert record["metadata"]["documents"] == 3 and record["metadata"]["link_id"]
    assert [event for event in timeline if event["action"] == "smart_upload_completed"] == []

    # A newer bank letter takes the drawer; the older one leaves it.
    newer = _pdf(tmp_path / "bank-new.pdf", [*_BANK_LINES[:-1], "112233"])
    replaced = _send(client, token, [("bank-new.pdf", newer)]).json()
    drawers = {item["document_type"]: item["filename"] for item in replaced["required_drawers"]}
    assert drawers["bank_confirmation"] == "bank-new.pdf" and replaced["all_drawers_filled"] is True
    workspace = client.get(f"/cases/{case_id}").json()
    assert workspace["case"]["document_count"] == 3
    assert workspace["field_values"]["bank_account"] == "112233"
    assert "112233" not in json.dumps(replaced, ensure_ascii=False)


def test_a_client_names_the_drawer_of_one_file_and_bad_drops_are_refused(client: TestClient, tmp_path: Path) -> None:
    case_id = _new(client)
    token = _link(client, case_id)["token"]
    plain = _pdf(tmp_path / "scan.pdf", ["מסמך סרוק"])

    # Nothing in the file says what it is: it is kept for the office, and no drawer is filled.
    waiting = _send(client, token, [("scan.pdf", plain)])
    assert waiting.status_code == 200, waiting.text
    held = waiting.json()
    _assert_public(held, {"routed_files"})
    assert [(item["outcome"], item["document_type"], item["label_he"]) for item in held["routed_files"]] == [
        ("pending", None, None)
    ]
    assert held["routed_files"][0]["reason_he"]
    assert not any(item["filled"] for item in held["required_drawers"])

    # The same kind of file, sent alone under the name the page gives the drawer.
    other = _pdf(tmp_path / "photo.pdf", ["צילום נוסף"])
    named = _send(client, token, [("photo.pdf", other)], field="file", document_type="id_card")
    assert named.status_code == 200, named.text
    chosen = named.json()
    assert [(item["outcome"], item["document_type"]) for item in chosen["routed_files"]] == [("received", "id_copy")]
    drawers = {item["document_type"]: item for item in chosen["required_drawers"]}
    assert drawers["id_copy"]["filled"] is True and drawers["id_copy"]["filename"] == "photo.pdf"
    assert chosen["all_drawers_filled"] is False

    before = client.get(f"/cases/{case_id}").json()
    six = [(f"file-{index}.pdf", _pdf(tmp_path / f"file-{index}.pdf", [f"מסמך {index}"])) for index in range(6)]
    assert _send(client, token, six).status_code == 400
    assert _send(client, token, six[:2], document_type="id_copy").status_code == 400
    assert _send(client, token, six[:1], document_type="payslip").status_code == 400
    with SignedOut(client) as anonymous:
        assert anonymous.post(f"/intake/{token}/upload").status_code == 400
    assert client.get(f"/cases/{case_id}").json() == before

    # A file that is not a document is refused by name, and the case stays as it was.
    junk = _send(client, token, [("notes.exe", b"MZ not a document")])
    assert junk.status_code == 200, junk.text
    assert [(item["filename"], item["outcome"]) for item in junk.json()["routed_files"]] == [("notes.exe", "rejected")]
    assert client.get(f"/cases/{case_id}").json()["case"]["document_count"] == before["case"]["document_count"]


def test_a_signed_case_and_an_expired_link_are_closed(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case_id = _new(client, "employee_onboarding")
    token = _link(client, case_id)["token"]
    assert client.post(f"/cases/{case_id}/load-default-form").status_code == 200
    assert _send(client, token, _everyday(tmp_path)).status_code == 200
    body: dict = {}
    for key, value in _TYPED.items():
        body = _set(client, case_id, key, value)
    assert body["ready_to_sign"] is True, body["signing_blockers"]
    assert _status(client, token).status_code == 200

    assert client.post(f"/cases/{case_id}/fill-and-sign", json=_sign_body()).status_code == 200
    signed = client.get(f"/cases/{case_id}").json()
    assert signed["case"]["status"] == "signed"

    # Once signed, the case takes no link and no file, and the link it had is gone.
    assert client.post(f"/cases/{case_id}/intake-link").status_code == 409
    assert _status(client, token).status_code == 410
    late = _pdf(tmp_path / "late.pdf", [*_BANK_LINES[:-1], "998877"])
    assert _send(client, token, [("bank.pdf", late)]).status_code == 410
    assert client.get(f"/cases/{case_id}").json() == signed

    # A link past its date is gone as well.
    other = _new(client)
    fresh = _link(client, other)["token"]
    assert _status(client, fresh).status_code == 200
    from app.core.time import utcnow
    from app.services import intake_service

    monkeypatch.setattr(intake_service, "utcnow", lambda: utcnow() + timedelta(days=8))
    assert _status(client, fresh).status_code == 410
    assert _send(client, fresh, _everyday(tmp_path)).status_code == 410
    monkeypatch.undo()
    assert _status(client, fresh).status_code == 200
    assert client.get(f"/cases/{other}").json()["case"]["document_count"] == 0

    # Deleting a case takes its link with it.
    assert client.delete(f"/cases/{other}").status_code in {200, 204}
    assert _status(client, fresh).status_code == 404


# The audit trail as a file


def test_the_audit_trail_downloads_as_csv_with_the_screens_filters(client: TestClient, tmp_path: Path) -> None:
    empty = _csv(client)
    assert empty == []

    first = _new(client)
    token = _link(client, first)["token"]
    assert _send(client, token, _everyday(tmp_path)).status_code == 200
    second = _new(client, "real_estate", client_name="=HYPERLINK(1)")
    _link(client, second)

    rows = _csv(client)
    listed = client.get("/audit", params={"limit": 500}).json()
    assert listed["total_events"] == len(rows) == listed["matched_events"]
    # The file is the screen's list: the same events, in the same order.
    assert [row["event_id"] for row in rows] == [event["event_id"] for event in listed["events"]]
    assert [row["action"] for row in rows] == [event["action"] for event in listed["events"]]
    assert {row["case_id"] for row in rows} == {first, second}
    assert all(row["created_at"].endswith("+00:00") and row["event_id"] and row["actor"] for row in rows)

    upload = _csv(client, action="client_intake_uploaded")
    assert len(upload) == 1
    assert upload[0] == {
        **upload[0],
        "case_id": first,
        "client_name": _DANA,
        "process_type": "bl_6101",
        "action": "client_intake_uploaded",
        "actor": _CLIENT_ACTOR,
    }
    links = _csv(client, action="intake_link_created")
    assert sorted(row["case_id"] for row in links) == sorted([first, second])

    searched = _csv(client, q="real_estate")
    assert searched and {row["case_id"] for row in searched} == {second}
    assert len(searched) == client.get("/audit", params={"q": "real_estate"}).json()["matched_events"]
    both = _csv(client, q=_DANA, action="intake_link_created")
    assert [row["case_id"] for row in both] == [first]
    assert _csv(client, q="אין תיק כזה") == []

    # A name that looks like a formula reaches the spreadsheet as text.
    assert {row["client_name"] for row in searched} == {"'=HYPERLINK(1)"}
    # Who did what and when. Nothing a document said.
    # The ids are random hex and could hold a short run of digits by chance, so only the other columns are read.
    told = json.dumps(
        [
            [row["client_name"], row["process_type"], row["action"], "" if row["actor"].startswith("user:") else row["actor"]]
            for row in rows
        ],
        ensure_ascii=False,
    )
    for value in _PRIVATE:
        assert value not in told, value

    assert client.get("/audit/export.csv", params={"action": "no_such_action"}).status_code == 400
    with SignedOut(client) as anonymous:
        assert anonymous.get("/audit/export.csv").status_code == 401


def test_the_audit_file_never_holds_another_offices_events(client: TestClient, tmp_path: Path) -> None:
    mine = _new(client)
    _link(client, mine)
    headers = _other_office(client)
    theirs = _new(client, client_name="רון לוי", headers=headers)
    token = _link(client, theirs, headers=headers)["token"]
    assert _send(client, token, _everyday(tmp_path)).status_code == 200

    own = _csv(client)
    assert own and {row["case_id"] for row in own} == {mine}
    raw = client.get("/audit/export.csv").content.decode("utf-8-sig")
    assert theirs not in raw and "רון לוי" not in raw and _CLIENT_ACTOR not in raw
    assert _csv(client, q="רון לוי") == [] and _csv(client, action="client_intake_uploaded") == []

    other = _csv(client, headers=headers)
    assert other and {row["case_id"] for row in other} == {theirs}
    assert [row["actor"] for row in _csv(client, headers=headers, action="client_intake_uploaded")] == [_CLIENT_ACTOR]
    assert mine not in client.get("/audit/export.csv", headers=headers).content.decode("utf-8-sig")
