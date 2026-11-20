"""Messages to clients: email and WhatsApp links, reminders, and when reminders stop on their own."""

from datetime import datetime, timedelta, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import unquote

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.domain.case_scope import CaseScope
from app.domain.outreach import ISRAEL, clean_email, clean_phone, reminder_at, whatsapp_url
from app.models.audit_log import AuditLog
from app.models.outreach import CaseOutreach
from tests.support import authenticate

_PUBLISHED = Path(__file__).resolve().parents[2] / "web" / "public" / "demo"
_DOCS = {"01-teudat-zehut.pdf": "id_copy", "02-arnona.pdf": "proof_of_address", "03-ishur-bank.pdf": "bank_confirmation"}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("FORM_101_TEMPLATE_PATH", str(tmp_path / "server" / "form_101.pdf"))
    monkeypatch.setenv("OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setenv("EMAIL_BACKEND", "outbox")
    monkeypatch.setenv("PUBLIC_WEB_URL", "https://office.example")
    monkeypatch.setenv("QUEUE_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("REMINDER_DAYS", "2,5")
    # Reminders may go out whatever the hour and day the test runs on.
    monkeypatch.setattr("app.services.outreach_service.allowed_now", lambda *_args, **_kw: True)
    from app.db.session import reset_db

    get_settings.cache_clear()
    reset_db()
    from app.main import app

    with TestClient(app) as test_client:
        authenticate(test_client)
        yield test_client
    reset_db()
    get_settings.cache_clear()


def _case(client: TestClient) -> str:
    created = client.post(
        "/cases", json={"name": "טופס 101", "process_key": "employee_onboarding", "client_name": "דנה כהן"}
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _outbox(tmp_path: Path) -> list:
    folder = tmp_path / "outbox"
    if not folder.exists():
        return []
    return [BytesParser(policy=policy.default).parsebytes(path.read_bytes()) for path in sorted(folder.glob("*.eml"))]


def _send(client: TestClient, case_id: str, **body):
    payload = {"purpose": "intake", "channel": "email", "email": "dana@example.com", **body}
    return client.post(f"/cases/{case_id}/outreach/send", json=payload)


def _due_now(client: TestClient, case_id: str) -> None:
    async def move() -> None:
        async with session_scope() as session:
            row = await session.get(CaseOutreach, __import__("uuid").UUID(case_id))
            assert row is not None
            row.next_reminder_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()

    client.portal.call(move)


def _run_reminders(client: TestClient) -> int:
    from app.services.outreach_service import OutreachService

    async def run() -> int:
        async with session_scope() as session:
            return await OutreachService(session, client.app.state.container, CaseScope.system()).send_due_emails()

    return client.portal.call(run)


# ---------------------------------------------------------------------------------------------
# Pure rules.
# ---------------------------------------------------------------------------------------------


def test_phone_numbers_become_whatsapp_numbers() -> None:
    assert clean_phone("050-123-4567") == "972501234567"
    assert clean_phone("+972 50 123 4567") == "972501234567"
    assert clean_phone("00972501234567") == "972501234567"
    assert clean_phone("03-1234567") is None
    assert clean_phone("hello") is None


def test_an_email_cannot_carry_a_second_header() -> None:
    assert clean_email(" Dana@Example.com ") == "dana@example.com"
    assert clean_email("dana@example.com\nBcc: x@evil.test") is None
    assert clean_email("Dana <dana@example.com>") is None


def test_the_whatsapp_link_carries_the_whole_message() -> None:
    url = whatsapp_url("972501234567", "שלום\nhttps://office.example/upload/abc")
    assert url.startswith("https://wa.me/972501234567?text=")
    assert unquote(url.split("text=", 1)[1]) == "שלום\nhttps://office.example/upload/abc"


def test_reminders_skip_the_night_and_saturday() -> None:
    # Thursday 23:00 Israel time + 2 days = Saturday 23:00 → Sunday 09:00.
    sent = datetime(2026, 11, 19, 23, 0, tzinfo=ISRAEL)
    due = reminder_at(sent, 0, [2, 5], start_hour=9, end_hour=20)
    assert due is not None
    local = due.astimezone(ISRAEL)
    assert (local.weekday(), local.hour) == (6, 9)
    assert reminder_at(sent, 2, [2, 5], start_hour=9, end_hour=20) is None


# ---------------------------------------------------------------------------------------------
# Sending.
# ---------------------------------------------------------------------------------------------


def test_an_email_carries_a_working_link_and_schedules_a_reminder(client: TestClient, tmp_path: Path) -> None:
    case_id = _case(client)
    sent = _send(client, case_id)
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert body["message"]["status"] == "sent"
    assert body["whatsapp_url"] is None
    assert body["next_reminder_at"] is not None
    assert body["url"].startswith("https://office.example/upload/")

    [mail] = _outbox(tmp_path)
    assert mail["To"] == "dana@example.com"
    assert "מסמכים" in mail["Subject"]
    assert body["url"] in mail.get_body(preferencelist=("plain",)).get_content()
    token = body["url"].rsplit("/", 1)[-1]
    assert client.get(f"/intake/{token}").status_code == 200

    state = client.get(f"/cases/{case_id}/outreach").json()
    assert state["email"] == "dana@example.com"
    assert state["reminders_enabled"] is True
    assert [item["kind"] for item in state["messages"]] == ["first"]

    async def audit() -> list[dict]:
        async with session_scope() as session:
            rows = await session.scalars(select(AuditLog).where(AuditLog.action == "client_message_sent"))
            return [row.new_value for row in rows]

    [entry] = client.portal.call(audit)
    assert entry["to"] == "d***@example.com"


def test_whatsapp_hands_the_office_a_link_and_sends_nothing(client: TestClient, tmp_path: Path) -> None:
    case_id = _case(client)
    sent = _send(client, case_id, channel="whatsapp", email=None, phone="050-1234567")
    assert sent.status_code == 201, sent.text
    body = sent.json()
    assert body["message"]["status"] == "handed_to_office"
    assert body["message"]["recipient"] == "050-1234567"
    assert body["whatsapp_url"].startswith("https://wa.me/972501234567?text=")
    assert body["url"] in unquote(body["whatsapp_url"])
    assert _outbox(tmp_path) == []


def test_a_new_message_replaces_the_link_before_it(client: TestClient) -> None:
    case_id = _case(client)
    first = _send(client, case_id).json()["url"].rsplit("/", 1)[-1]
    second = _send(client, case_id).json()["url"].rsplit("/", 1)[-1]
    assert first != second
    assert client.get(f"/intake/{first}").status_code == 410
    assert client.get(f"/intake/{second}").status_code == 200


def test_bad_contact_details_are_refused(client: TestClient) -> None:
    case_id = _case(client)
    assert _send(client, case_id, email="not-an-address").status_code == 400
    assert _send(client, case_id, channel="whatsapp", email=None, phone="03-1234567").status_code == 400
    assert _send(client, case_id, channel="whatsapp", email=None).status_code == 400


def test_email_off_on_the_server_still_allows_whatsapp(client: TestClient) -> None:
    get_settings().email_backend = "disabled"
    case_id = _case(client)
    assert _send(client, case_id).status_code == 409
    assert _send(client, case_id, channel="whatsapp", email=None, phone="0501234567").status_code == 201


def test_a_case_gets_a_limited_number_of_messages_a_day(client: TestClient) -> None:
    get_settings().max_messages_per_case_per_day = 2
    case_id = _case(client)
    assert _send(client, case_id).status_code == 201
    assert _send(client, case_id).status_code == 201
    refused = _send(client, case_id)
    assert refused.status_code == 429


# ---------------------------------------------------------------------------------------------
# Reminders.
# ---------------------------------------------------------------------------------------------


def test_a_due_reminder_goes_out_once_with_the_same_link(client: TestClient, tmp_path: Path) -> None:
    case_id = _case(client)
    url = _send(client, case_id).json()["url"]
    assert _run_reminders(client) == 0  # nothing is due yet
    _due_now(client, case_id)
    assert _run_reminders(client) == 1
    assert _run_reminders(client) == 0  # claimed and rescheduled, not sent twice

    first, reminder = _outbox(tmp_path)
    assert "תזכורת" in reminder["Subject"]
    assert url in reminder.get_body(preferencelist=("plain",)).get_content()
    state = client.get(f"/cases/{case_id}/outreach").json()
    assert state["reminders_sent"] == 1
    assert state["next_reminder_at"] is not None
    assert [item["kind"] for item in state["messages"]] == ["reminder", "first"]


def test_reminders_stop_when_every_document_is_in(client: TestClient, tmp_path: Path) -> None:
    case_id = _case(client)
    _send(client, case_id)
    for name, type_key in _DOCS.items():
        uploaded = client.post(
            f"/cases/{case_id}/upload",
            files=[("files", (name, (_PUBLISHED / name).read_bytes(), "application/pdf"))],
            data={"document_type": type_key},
        )
        assert uploaded.status_code == 200, uploaded.text
    _due_now(client, case_id)
    assert _run_reminders(client) == 0
    assert len(_outbox(tmp_path)) == 1
    assert client.get(f"/cases/{case_id}/outreach").json()["stopped_reason"] == "done"


def test_reminders_stop_when_the_office_makes_another_link(client: TestClient) -> None:
    case_id = _case(client)
    _send(client, case_id)
    assert client.post(f"/cases/{case_id}/intake-link").status_code == 201
    _due_now(client, case_id)
    assert _run_reminders(client) == 0
    assert client.get(f"/cases/{case_id}/outreach").json()["stopped_reason"] == "link_replaced"


def test_the_office_can_turn_reminders_off_and_on(client: TestClient) -> None:
    case_id = _case(client)
    _send(client, case_id)
    off = client.put(f"/cases/{case_id}/outreach/reminders", json={"enabled": False}).json()
    assert off["reminders_enabled"] is False and off["stopped_reason"] == "turned_off"
    _due_now(client, case_id)
    assert _run_reminders(client) == 0
    on = client.put(f"/cases/{case_id}/outreach/reminders", json={"enabled": True}).json()
    assert on["reminders_enabled"] is True and on["next_reminder_at"] is not None


def test_whatsapp_reminders_wait_for_the_office(client: TestClient, tmp_path: Path) -> None:
    case_id = _case(client)
    _send(client, case_id, channel="whatsapp", email=None, phone="0501234567")
    assert client.get("/outreach/due").json() == []
    _due_now(client, case_id)
    assert _run_reminders(client) == 0  # never sent by itself
    [due] = client.get("/outreach/due").json()
    assert due["case_id"] == case_id and due["phone_display"] == "050-1234567"

    reminded = client.post(f"/cases/{case_id}/outreach/remind")
    assert reminded.status_code == 200, reminded.text
    assert "תזכורת" in unquote(reminded.json()["whatsapp_url"])
    assert client.get("/outreach/due").json() == []
    assert client.get(f"/cases/{case_id}/outreach").json()["reminders_sent"] == 1
    assert _outbox(tmp_path) == []


def test_another_office_cannot_see_or_message_this_client(client: TestClient) -> None:
    case_id = _case(client)
    _send(client, case_id)
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    assert client.get(f"/cases/{case_id}/outreach", headers=headers).status_code == 404
    assert client.post(f"/cases/{case_id}/outreach/remind", headers=headers).status_code == 404
    assert client.get("/outreach/due", headers=headers).json() == []
