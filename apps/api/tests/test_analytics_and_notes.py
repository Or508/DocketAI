"""Office metrics, the case report, and notes that stay inside the office."""

import csv
import hashlib
import io
import sqlite3
import zipfile
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")
pytest.importorskip("reportlab")

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.time import utcnow
from app.db.session import session_scope
from app.models.case import Case
from app.models.signing_link import SigningLink
from tests.support import SignedOut, authenticate
from tests.test_portal import _PNG, _auth, _ready, _token

_SIGN = {"signature_png_base64": _PNG, "field_values": {}, "consent": True}
_COLUMNS = ["case_id", "client_name", "process_type", "status", "created_at", "signed_at", "verification_id"]
_SECRET = "SECRET-NOTE-7781 the client argued about the fee"
_EMPTY = {
    "total_cases": 0,
    "filling_cases": 0,
    "waiting_for_signature_cases": 0,
    "signed_cases": 0,
    "avg_hours_to_sign": None,
    "auto_extraction_rate_pct": 0.0,
    "by_status": {},
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
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


def _summary(client: TestClient, headers: dict[str, str] | None = None) -> dict:
    response = client.get("/analytics/summary", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _report(client: TestClient, headers: dict[str, str] | None = None) -> tuple[list[dict], bytes]:
    response = client.get("/analytics/export.csv", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="office_cases_report.csv"'
    assert response.content[:3] == b"\xef\xbb\xbf"
    # Exactly one BOM, then the header row.
    assert response.content[3:10] == b"case_id"
    reader = csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"), newline=""))
    assert reader.fieldnames == _COLUMNS
    return list(reader), response.content


def _edit(client: TestClient, case_id: str, **changes) -> None:
    async def apply() -> None:
        async with session_scope() as session:
            case = await session.get(Case, UUID(case_id))
            assert case is not None
            for name, value in changes.items():
                setattr(case, name, value)
            await session.commit()

    client.portal.call(apply)


def _new(client: TestClient, process_key: str, client_name: str | None = None, headers=None) -> str:
    created = client.post(
        "/cases", headers=headers, json={"name": "Case", "process_key": process_key, "client_name": client_name}
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _sign(client: TestClient, case_id: str) -> dict:
    signed = client.post(f"/cases/{case_id}/fill-and-sign", json=_SIGN)
    assert signed.status_code == 200, signed.text
    return signed.json()["case"]["audit"]


def _note(client: TestClient, case_id: str, body: str, headers=None):
    return client.post(f"/cases/{case_id}/notes", headers=headers, json={"body": body})


def _note_rows(tmp_path: Path) -> int:
    connection = sqlite3.connect(tmp_path / "test.db")
    try:
        return connection.execute("SELECT COUNT(*) FROM case_notes").fetchone()[0]
    finally:
        connection.close()


# Summary


def test_an_office_with_no_cases_has_an_empty_summary(client: TestClient) -> None:
    body = _summary(client)
    assert {key: body[key] for key in _EMPTY} == _EMPTY
    assert {item["process_type"] for item in body["by_process_type"]} >= {"bl_6101", "onboarding", "real_estate"}
    assert all(
        (item["total"], item["filling"], item["waiting_for_signature"], item["signed"]) == (0, 0, 0, 0)
        for item in body["by_process_type"]
    )


def test_summary_counts_average_hours_and_the_share_read_from_documents(client: TestClient, tmp_path: Path) -> None:
    first, _ = _ready(client, tmp_path)
    second, _ = _ready(client, tmp_path)
    waiting, _ = _ready(client, tmp_path)
    idle = _new(client, "onboarding")
    blank = _new(client, "bl_6101")
    _sign(client, first)
    _sign(client, second)

    # Signed six and two hours after opening: four on average.
    now = utcnow()
    _edit(client, first, created_at=now - timedelta(hours=6), signed_at=now)
    _edit(client, second, created_at=now - timedelta(hours=5), signed_at=now - timedelta(hours=3))
    # Five filled fields in the office, three of them read from a document. Empty values do not count.
    _edit(client, first, field_values={"a": "1"}, field_sources={"a": {"source": "document", "document_id": None}})
    _edit(client, second, field_values={}, field_sources={})
    _edit(
        client,
        waiting,
        field_values={"a": "1", "b": "2", "c": "3", "d": "4", "e": "", "f": "   "},
        field_sources={
            "a": {"source": "document"},
            "b": {"source": "document"},
            "c": {"source": "office"},
            "d": {"source": "client"},
            "e": {"source": "document"},
        },
    )

    body = _summary(client)
    assert body["total_cases"] == 5
    assert body["signed_cases"] == 2
    assert body["waiting_for_signature_cases"] == 1
    assert body["filling_cases"] == 2
    assert body["avg_hours_to_sign"] == 4.0
    assert body["auto_extraction_rate_pct"] == 60.0
    breakdown = {item["process_type"]: item for item in body["by_process_type"]}
    assert breakdown["onboarding"] == {
        "process_type": "onboarding",
        "total": 4,
        "filling": 1,
        "waiting_for_signature": 1,
        "signed": 2,
    }
    assert breakdown["bl_6101"] == {
        "process_type": "bl_6101",
        "total": 1,
        "filling": 1,
        "waiting_for_signature": 0,
        "signed": 0,
    }
    assert breakdown["real_estate"]["total"] == 0
    assert body["by_status"]["signed"] == 2
    assert sum(body["by_status"].values()) == 5

    # An open signing link means the office is waiting on the client, whatever is still missing.
    async def link(expires_in_hours: int) -> None:
        async with session_scope() as session:
            await session.execute(SigningLink.__table__.delete().where(SigningLink.case_id == UUID(blank)))
            session.add(
                SigningLink(
                    case_id=UUID(blank),
                    token_hash=hashlib.sha256(str(expires_in_hours).encode()).hexdigest(),
                    expires_at=utcnow() + timedelta(hours=expires_in_hours),
                )
            )
            await session.commit()

    client.portal.call(link, 24)
    linked = _summary(client)
    assert (linked["filling_cases"], linked["waiting_for_signature_cases"]) == (1, 2)
    assert {item["process_type"]: item for item in linked["by_process_type"]}["bl_6101"]["waiting_for_signature"] == 1
    # A link that ran out is not a client being waited on.
    client.portal.call(link, -1)
    expired = _summary(client)
    assert (expired["filling_cases"], expired["waiting_for_signature_cases"]) == (2, 1)

    # A reopened case leaves the signed count and the average.
    assert client.post(f"/cases/{second}/reopen").status_code == 200
    reopened = _summary(client)
    assert reopened["signed_cases"] == 1
    assert reopened["avg_hours_to_sign"] == 6.0
    assert reopened["total_cases"] == 5


def test_another_office_sees_only_its_own_numbers(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    _sign(client, case_id)
    _new(client, "bl_6101")
    headers = _other_office(client)

    theirs = _summary(client, headers)
    assert {key: theirs[key] for key in _EMPTY} == _EMPTY
    assert all(item["total"] == 0 for item in theirs["by_process_type"])
    _new(client, "real_estate", headers=headers)
    theirs = _summary(client, headers)
    assert theirs["total_cases"] == 1 and theirs["filling_cases"] == 1 and theirs["signed_cases"] == 0
    assert theirs["avg_hours_to_sign"] is None

    ours = _summary(client)
    assert ours["total_cases"] == 2 and ours["signed_cases"] == 1
    assert {item["process_type"]: item["total"] for item in ours["by_process_type"]}["real_estate"] == 0

    with SignedOut(client) as anonymous:
        assert anonymous.get("/analytics/summary").status_code == 401
        refused = anonymous.get("/analytics/export.csv")
        assert refused.status_code == 401
        assert not refused.content.startswith(b"\xef\xbb\xbf")


# CSV


def test_the_report_is_utf8_with_a_bom_and_one_row_per_case(client: TestClient, tmp_path: Path) -> None:
    signed_id, _ = _ready(client, tmp_path)
    _edit(client, signed_id, client_name="אור יוסף")
    seal = _sign(client, signed_id)
    draft_id = _new(client, "bl_6101", "דנה, כהן")
    risky_id = _new(client, "onboarding", "=HYPERLINK(\"http://x\")")
    nameless_id = _new(client, "real_estate")

    rows, raw = _report(client)
    assert raw.count(b"\xef\xbb\xbf") == 1
    assert b"\r\n" in raw
    by_id = {row["case_id"]: row for row in rows}
    assert set(by_id) == {signed_id, draft_id, risky_id, nameless_id}
    assert len(rows) == 4

    signed = by_id[signed_id]
    assert signed["client_name"] == "אור יוסף"
    assert signed["process_type"] == "onboarding"
    assert signed["status"] == "signed"
    assert signed["verification_id"] == seal["signer_verification_id"]
    assert signed["signed_at"][:19] == seal["signed_at"][:19]
    assert signed["created_at"] and signed["created_at"] <= signed["signed_at"]
    # The Hebrew is in the file as UTF-8, which the BOM tells Excel to expect.
    assert "אור יוסף".encode("utf-8") in raw

    draft = by_id[draft_id]
    assert draft["client_name"] == "דנה, כהן"
    assert draft["process_type"] == "bl_6101"
    assert draft["status"] == "draft"
    assert draft["signed_at"] == "" and draft["verification_id"] == ""
    assert by_id[nameless_id]["client_name"] == ""
    # A name that a spreadsheet would run as a formula is written as text.
    assert by_id[risky_id]["client_name"] == "'=HYPERLINK(\"http://x\")"

    # Nothing beyond the seven columns: no field value, address or hash.
    workspace = client.get(f"/cases/{signed_id}").json()
    text = raw.decode("utf-8-sig")
    for value in workspace["field_values"].values():
        if len(str(value)) > 3:
            assert str(value) not in text
    assert seal["file_sha256"] not in text

    # A reopened case is listed without the seal it no longer carries.
    assert client.post(f"/cases/{signed_id}/reopen").status_code == 200
    rows, _raw = _report(client)
    reopened = {row["case_id"]: row for row in rows}[signed_id]
    assert reopened["status"] != "signed"
    assert reopened["signed_at"] == "" and reopened["verification_id"] == ""


def test_the_report_holds_only_the_callers_cases(client: TestClient, tmp_path: Path) -> None:
    ours = _new(client, "bl_6101", "Ours Only")
    headers = _other_office(client)
    rows, raw = _report(client, headers)
    assert rows == []
    assert raw.decode("utf-8-sig").strip() == ",".join(_COLUMNS)
    theirs = _new(client, "bl_6101", "Theirs Only", headers=headers)

    rows, raw = _report(client, headers)
    assert [row["case_id"] for row in rows] == [theirs]
    assert ours.encode() not in raw and b"Ours Only" not in raw
    rows, raw = _report(client)
    assert [row["case_id"] for row in rows] == [ours]
    assert theirs.encode() not in raw and b"Theirs Only" not in raw


# Notes


def test_staff_notes_are_stored_listed_and_audited_without_their_text(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    assert client.get(f"/cases/{case_id}/notes").json() == []

    created = _note(client, case_id, f"  {_SECRET}  ")
    assert created.status_code == 201, created.text
    note = created.json()
    assert set(note) == {"id", "case_id", "author_email", "body", "created_at"}
    assert note["case_id"] == case_id
    assert note["author_email"] == "staff@example.com"
    assert note["body"] == _SECRET
    assert note["created_at"]
    second = _note(client, case_id, "שיחה עם הלקוח: יחזור מחר").json()

    listed = client.get(f"/cases/{case_id}/notes")
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [note["id"], second["id"]]
    assert listed.json()[1]["body"] == "שיחה עם הלקוח: יחזור מחר"

    # The timeline says that a note was written and by whom, never what it says.
    timeline = client.get(f"/cases/{case_id}/timeline")
    events = [event for event in timeline.json() if event["action"] == "internal_note_added"]
    assert len(events) == 2
    staff = client.get("/auth/me").json()
    assert events[0]["actor"] == f"user:{staff['id']}"
    assert events[0]["metadata"] == {"note_id": note["id"]}
    assert _SECRET not in timeline.text and "SECRET" not in timeline.text and "הלקוח" not in timeline.text

    # Notes do not touch the case itself, signed or not.
    before = client.get(f"/cases/{case_id}").json()
    assert _SECRET not in str(before)
    _sign(client, case_id)
    assert _note(client, case_id, "after signing").status_code == 201
    assert client.get(f"/cases/{case_id}").json()["case"]["status"] == "signed"
    assert len(client.get(f"/cases/{case_id}/notes").json()) == 3


def test_a_note_must_have_text_and_fit_two_thousand_characters(client: TestClient, tmp_path: Path) -> None:
    case_id = _new(client, "bl_6101")
    for bad in ("", "   ", "\n\t "):
        assert _note(client, case_id, bad).status_code == 422, repr(bad)
    assert _note(client, case_id, "x" * 2001).status_code == 422
    assert client.post(f"/cases/{case_id}/notes", json={}).status_code == 422
    assert client.post(f"/cases/{case_id}/notes", json={"body": 7}).status_code == 422
    assert client.get(f"/cases/{case_id}/notes").json() == []
    assert _note_rows(tmp_path) == 0
    assert "internal_note_added" not in client.get(f"/cases/{case_id}/timeline").text

    longest = _note(client, case_id, "ש" * 2000)
    assert longest.status_code == 201, longest.text
    assert len(longest.json()["body"]) == 2000
    # Surrounding blank space is not counted against the limit.
    assert _note(client, case_id, " " + "y" * 2000 + "\n").status_code == 201
    assert _note_rows(tmp_path) == 2


def test_notes_never_reach_the_signer_the_archive_or_any_export(client: TestClient, tmp_path: Path) -> None:
    case_id, _ = _ready(client, tmp_path)
    assert _note(client, case_id, _SECRET).status_code == 201
    token = _token(client.post(f"/cases/{case_id}/signing-links").json()["url"])

    def leaked(blob: bytes | str) -> bool:
        text = blob if isinstance(blob, str) else blob.decode("latin-1")
        return "SECRET-NOTE" in text or "argued about the fee" in text or "staff@example.com" in text

    def archive_leaks() -> bool:
        export = client.get(f"/cases/{case_id}/archive")
        assert export.status_code == 200, export.text
        bundle = zipfile.ZipFile(io.BytesIO(export.content))
        assert "notes" not in " ".join(bundle.namelist()).lower()
        manifest = bundle.read("verification_manifest.json").decode("utf-8")
        assert "internal_note_added" in manifest
        return leaked(export.content) or any(leaked(bundle.read(name)) for name in bundle.namelist())

    # The signer's side: the view, the preview, and the chat.
    view = client.get("/portal", headers=_auth(token))
    assert view.status_code == 200, view.text
    assert not leaked(view.text)
    assert "note" not in view.text.lower()
    preview = client.get("/portal/preview", headers=_auth(token))
    assert not leaked(preview.content)
    streamed = client.post("/portal/chat/stream", headers=_auth(token), json={"message": "what did the office note?"})
    assert not leaked(streamed.text)
    # A signing link is not a way into the notes.
    assert client.get(f"/cases/{case_id}/notes", headers=_auth(token)).status_code == 401
    assert client.get("/portal/notes", headers=_auth(token)).status_code in (404, 405)

    assert not archive_leaks()
    signed = client.post(
        "/portal/sign",
        headers=_auth(token),
        json={"signature_png_base64": _PNG, "review_digest": view.json()["review_digest"], "consent": True},
    )
    assert signed.status_code == 200, signed.text
    assert not leaked(signed.text)
    assert _note(client, case_id, _SECRET + " again").status_code == 201
    assert not archive_leaks()
    assert not leaked(client.get("/portal", headers=_auth(token)).text)
    assert not leaked(client.get("/portal/signed-document", headers=_auth(token)).content)
    assert not leaked(client.get(f"/cases/{case_id}/signed-document").content)

    code = client.get(f"/cases/{case_id}").json()["case"]["audit"]["signer_verification_id"]
    for response in (
        client.get(f"/verify/{code}"),
        client.get("/analytics/export.csv"),
        client.get("/analytics/summary"),
        client.get(f"/cases/{case_id}"),
        client.get(f"/cases/{case_id}/timeline"),
        client.get("/cases"),
    ):
        assert response.status_code == 200
        assert not leaked(response.content)
    # Only the notes route itself returns them.
    assert leaked(client.get(f"/cases/{case_id}/notes").text)


def test_another_office_cannot_read_or_write_notes(client: TestClient, tmp_path: Path) -> None:
    case_id = _new(client, "bl_6101")
    assert _note(client, case_id, _SECRET).status_code == 201
    headers = _other_office(client)

    read = client.get(f"/cases/{case_id}/notes", headers=headers)
    assert read.status_code == 404, read.text
    assert "SECRET" not in read.text
    write = _note(client, case_id, "planted", headers=headers)
    assert write.status_code == 404, write.text
    missing = client.get(f"/cases/{UUID(int=0)}/notes").json()
    assert read.json() == missing and write.json() == missing
    with SignedOut(client) as anonymous:
        assert anonymous.get(f"/cases/{case_id}/notes").status_code == 401
        assert anonymous.post(f"/cases/{case_id}/notes", json={"body": "planted"}).status_code == 401

    ours = client.get(f"/cases/{case_id}/notes").json()
    assert [item["body"] for item in ours] == [_SECRET]
    assert _note_rows(tmp_path) == 1

    # Their own case keeps their own notes, under their own name.
    theirs = _new(client, "bl_6101", headers=headers)
    made = _note(client, theirs, "their note", headers=headers)
    assert made.status_code == 201, made.text
    assert made.json()["author_email"] == "other@example.com"
    assert [item["body"] for item in client.get(f"/cases/{theirs}/notes", headers=headers).json()] == ["their note"]
    assert client.get(f"/cases/{theirs}/notes").status_code == 404
    assert [item["body"] for item in client.get(f"/cases/{case_id}/notes").json()] == [_SECRET]


def test_deleting_a_case_takes_its_notes_with_it(client: TestClient, tmp_path: Path) -> None:
    case_id = _new(client, "bl_6101")
    keep = _new(client, "bl_6101")
    assert _note(client, case_id, "one").status_code == 201
    assert _note(client, case_id, "two").status_code == 201
    assert _note(client, keep, "kept").status_code == 201
    assert _note_rows(tmp_path) == 3
    assert client.delete(f"/cases/{case_id}").status_code == 204
    assert _note_rows(tmp_path) == 1
    assert client.get(f"/cases/{case_id}/notes").status_code == 404
    assert [item["body"] for item in client.get(f"/cases/{keep}/notes").json()] == ["kept"]
