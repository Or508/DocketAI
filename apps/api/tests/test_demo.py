"""A public demo office: private to its visitor, short-lived, and unable to send email."""

import uuid
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.core.time import utcnow
from app.domain.enums import CaseStatus
from app.models.case import Case
from app.models.organization import Organization
from tests.support import SignedOut, authenticate

DEMO_EMAIL = "בדמו אפשר לשלוח רק בוואטסאפ, כדי שלא יישלחו מיילים לאנשים אמיתיים."
CAP = "הגעתם למכסת הדמו להיום. אפשר לנסות שוב מחר."


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("QUEUE_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    monkeypatch.setenv("OUTBOX_DIR", str(tmp_path / "outbox"))
    monkeypatch.setenv("EMAIL_BACKEND", "outbox")
    monkeypatch.setenv("PUBLIC_WEB_URL", "https://office.example")
    monkeypatch.setenv("DEMO_MODE", "true")
    from app.db.session import reset_db

    get_settings.cache_clear()
    reset_db()
    from app.main import app

    with TestClient(app) as test_client:
        authenticate(test_client, display_name="Owner")
        yield test_client
    reset_db()
    get_settings.cache_clear()


def _start(client: TestClient, scenario: str = "law") -> dict:
    with SignedOut(client) as anonymous:
        response = anonymous.post("/demo/start", json={"scenario": scenario})
    assert response.status_code == 200, response.text
    return response.json()


def _cases(client: TestClient, token: str) -> list[dict]:
    response = client.get("/cases", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200, response.text
    return response.json()


def test_start_signs_in_an_isolated_office(client: TestClient) -> None:
    first = _start(client, "law")
    second = _start(client, "hr")
    assert first["user"]["demo_expires_at"]
    assert first["user"]["email"].endswith("@demo.invalid")
    mine = _cases(client, first["token"])
    theirs = _cases(client, second["token"])
    assert len(mine) >= 2
    assert len(theirs) >= 2
    assert {row["id"] for row in mine}.isdisjoint({row["id"] for row in theirs})
    # One case per scenario arrives with the sample documents; the others start empty on purpose.
    assert sum(1 for row in mine if row["document_count"] >= 1) == 1
    office = client.get("/auth/me")
    assert office.status_code == 200
    assert office.json()["demo_expires_at"] is None


def test_daily_cap(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_STARTS_PER_IP_PER_DAY", "2")
    get_settings.cache_clear()
    assert _start(client)["token"]
    assert _start(client)["token"]
    with SignedOut(client) as anonymous:
        blocked = anonymous.post("/demo/start", json={"scenario": "dental"})
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == CAP


def test_demo_refuses_email_and_ignores_password_reset(client: TestClient, tmp_path: Path) -> None:
    started = _start(client, "dental")
    headers = {"Authorization": f"Bearer {started['token']}"}
    invited = client.post(
        "/team/invite",
        headers=headers,
        json={"email": "person@example.com", "display_name": "נועה", "role": "staff"},
    )
    assert invited.status_code == 403
    assert invited.json()["detail"] == DEMO_EMAIL
    before = list((tmp_path / "outbox").glob("*.eml"))
    with SignedOut(client) as anonymous:
        forgot = anonymous.post("/account/password/forgot", json={"email": started["user"]["email"]})
    assert forgot.status_code == 202
    assert list((tmp_path / "outbox").glob("*.eml")) == before


def test_cleanup_removes_only_the_expired_demo(client: TestClient, tmp_path: Path) -> None:
    expired = _start(client, "law")
    kept = _start(client, "hr")
    real = {row["id"] for row in client.get("/cases").json()}
    org_id = uuid.UUID(expired["user"]["organization_id"]) if "organization_id" in expired["user"] else None

    async def mark() -> str:
        from app.db.session import session_scope

        async with session_scope() as session:
            user_email = expired["user"]["email"]
            from app.models.user import User

            user = await session.scalar(select(User).where(User.email == user_email))
            assert user is not None
            org = await session.get(Organization, user.organization_id)
            assert org is not None and org.demo_expires_at is not None
            org.demo_expires_at = utcnow() - timedelta(hours=1)
            case = await session.scalar(select(Case).where(Case.organization_id == org.id))
            assert case is not None
            case.status = CaseStatus.SIGNED
            await session.commit()
            return str(org.id)

    demo_org = client.portal.call(mark)
    assert org_id is None or str(org_id) == demo_org
    stored = [path for path in (tmp_path / "storage").rglob("*") if path.is_file()]
    assert any(demo_org in path.as_posix() for path in stored)

    async def sweep() -> int:
        from app.services.demo_service import delete_expired_demos

        return await delete_expired_demos(client.app.state.container)

    assert client.portal.call(sweep) == 1
    gone = client.get("/cases", headers={"Authorization": f"Bearer {expired['token']}"})
    assert gone.status_code == 401
    assert {row["id"] for row in _cases(client, kept["token"])}
    assert {row["id"] for row in client.get("/cases").json()} == real
    left = [path for path in (tmp_path / "storage").rglob("*") if path.is_file() and demo_org in path.as_posix()]
    assert left == []

    async def still_there() -> bool:
        from app.db.session import session_scope

        async with session_scope() as session:
            org = await session.get(Organization, uuid.UUID(demo_org))
            real_org = await session.scalar(select(Organization).where(Organization.name == "Test office"))
            return org is None and real_org is not None and real_org.demo_expires_at is None

    assert client.portal.call(still_there)


def test_start_is_hidden_when_demo_mode_is_off(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    get_settings.cache_clear()
    with SignedOut(client) as anonymous:
        hidden = anonymous.post("/demo/start", json={"scenario": "law"})
        info = anonymous.get("/demo/info")
    assert hidden.status_code == 404
    assert info.status_code == 200
    assert info.json()["enabled"] is False


import pytest  # noqa: E402


@pytest.mark.parametrize("scenario", ["law", "dental", "hr"])
def test_each_scenario_has_a_case_ready_for_a_signer(client: TestClient, scenario: str) -> None:
    demo = _start(client, scenario)
    headers = {"Authorization": f"Bearer {demo['token']}"}
    ready = [row for row in _cases(client, demo["token"]) if row["document_count"] >= 1]
    assert len(ready) == 1
    # The sample documents belong to one invented person; the case must carry her name.
    assert ready[0]["client_name"] == "דנה כהן"
    workspace = client.get(f"/cases/{ready[0]['id']}", headers=headers).json()
    # Only the client's own phone is left for the signer to add.
    assert {field["key"] for field in workspace["missing_fields"]} <= {"phone"}
    link = client.post(f"/cases/{ready[0]['id']}/signing-links", headers=headers)
    assert link.status_code == 201, link.text


def test_a_demo_office_cannot_turn_ai_reading_on(client: TestClient) -> None:
    demo = _start(client)
    headers = {"Authorization": f"Bearer {demo['token']}"}
    refused = client.put("/organization/ai-reading", json={"enabled": True}, headers=headers)
    assert refused.status_code == 403
    assert "AI" in refused.json()["detail"]
    assert client.get("/organization", headers=headers).json()["ai_reading_enabled"] is False


def test_the_demo_phone_reads_and_dials_like_an_israeli_number(client: TestClient) -> None:
    from app.services.demo_service import local_phone

    assert local_phone("972547302757") == "054-7302757"
    assert local_phone("0547302757") == "054-7302757"
    demo = _start(client)
    office = client.get("/organization", headers={"Authorization": f"Bearer {demo['token']}"}).json()
    assert office["contact_phone"] == "054-7302757"
