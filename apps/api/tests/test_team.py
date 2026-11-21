"""Office people: roles, invitations, turning accounts off, and "forgot my password"."""

import re
from datetime import timedelta
from email import policy
from email.parser import BytesParser
from pathlib import Path

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.core.config import get_settings
from app.core.time import utcnow
from app.db.session import session_scope
from app.models.account_token import AccountToken
from app.models.user import User
from app.models.user_session import UserSession
from tests.support import PASSWORD, SignedOut, authenticate

NEW_PASSWORD = "a-brand-new-passphrase"


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
    from app.db.session import reset_db

    get_settings.cache_clear()
    reset_db()
    from app.main import app

    with TestClient(app) as test_client:
        authenticate(test_client, display_name="Owner")
        yield test_client
    reset_db()
    get_settings.cache_clear()


def _outbox(tmp_path: Path) -> list:
    folder = tmp_path / "outbox"
    if not folder.exists():
        return []
    return [BytesParser(policy=policy.default).parsebytes(path.read_bytes()) for path in sorted(folder.glob("*.eml"))]


def _token(url: str, kind: str) -> str:
    match = re.search(rf"/{kind}/([A-Za-z0-9_-]+)", url)
    assert match, url
    return match.group(1)


def _invite(client: TestClient, email: str = "noa@example.com", role: str = "staff") -> dict:
    response = client.post("/team/invite", json={"email": email, "display_name": "נועה", "role": role})
    assert response.status_code == 201, response.text
    return response.json()


def _login(client: TestClient, email: str, password: str):
    with SignedOut(client) as anonymous:
        return anonymous.post("/auth/login", json={"email": email, "password": password})


def _as(client: TestClient, token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_the_first_user_is_an_owner_and_me_says_so(client: TestClient) -> None:
    assert client.get("/auth/me").json()["role"] == "owner"
    [me] = client.get("/team").json()
    assert me["status"] == "active" and me["is_you"] and me["role"] == "owner"


def test_an_invited_colleague_joins_with_their_own_password(client: TestClient, tmp_path: Path) -> None:
    result = _invite(client)
    assert result["email_sent"] is True
    assert result["member"]["status"] == "invited"
    [mail] = _outbox(tmp_path)
    assert mail["To"] == "noa@example.com"
    body = mail.get_body(("plain",)).get_content()
    assert result["invite_url"] in body
    token = _token(result["invite_url"], "join")

    # Until they choose a password, nobody can sign in as them.
    assert _login(client, "noa@example.com", PASSWORD).status_code == 401

    with SignedOut(client) as anonymous:
        info = anonymous.post("/account/link", json={"token": token})
        assert info.status_code == 200, info.text
        assert info.json()["purpose"] == "invite"
        assert info.json()["organization_name"] == "Test office"
        short = anonymous.post("/account/invite/accept", json={"token": token, "password": "short"})
        assert short.status_code == 400 and short.json()["code"] == "weak_password"
        accepted = anonymous.post("/account/invite/accept", json={"token": token, "password": NEW_PASSWORD})
        assert accepted.status_code == 204, accepted.text
        # The link works once.
        again = anonymous.post("/account/invite/accept", json={"token": token, "password": NEW_PASSWORD})
        assert again.status_code == 410

    signed_in = _login(client, "noa@example.com", NEW_PASSWORD)
    assert signed_in.status_code == 200, signed_in.text
    assert signed_in.json()["user"]["role"] == "staff"
    statuses = {member["email"]: member["status"] for member in client.get("/team").json()}
    assert statuses == {"staff@example.com": "active", "noa@example.com": "active"}


def test_only_the_token_hash_is_stored(client: TestClient) -> None:
    token = _token(_invite(client)["invite_url"], "join")

    async def hashes() -> list[str]:
        async with session_scope() as session:
            return list(await session.scalars(select(AccountToken.token_hash)))

    stored = client.portal.call(hashes)
    assert stored and token not in stored[0]


def test_staff_cannot_invite_or_change_office_settings(client: TestClient) -> None:
    token = _token(_invite(client)["invite_url"], "join")
    with SignedOut(client) as anonymous:
        anonymous.post("/account/invite/accept", json={"token": token, "password": NEW_PASSWORD})
    staff = _login(client, "noa@example.com", NEW_PASSWORD).json()["token"]
    headers = _as(client, staff)

    assert client.get("/team", headers=headers).status_code == 200
    blocked = client.post("/team/invite", json={"email": "x@example.com", "display_name": "x"}, headers=headers)
    assert blocked.status_code == 403
    assert client.put("/organization/ai-reading", json={"enabled": False}, headers=headers).status_code == 403
    assert client.put("/organization/profession", json={"profession": "dental"}, headers=headers).status_code == 403
    owner_id = next(m["id"] for m in client.get("/team").json() if m["role"] == "owner")
    assert client.patch(f"/team/{owner_id}", json={"is_active": False}, headers=headers).status_code == 403
    # Staff still work on cases.
    assert client.get("/cases", headers=headers).status_code == 200


def test_inviting_an_existing_address_is_refused(client: TestClient) -> None:
    _invite(client)
    again = client.post("/team/invite", json={"email": "NOA@example.com", "display_name": "נועה"})
    assert again.status_code == 409 and again.json()["code"] == "already_member"
    bad = client.post("/team/invite", json={"email": "not-an-email", "display_name": "x"})
    assert bad.status_code == 400 and bad.json()["code"] == "bad_email"


def test_another_office_cannot_see_or_change_our_people(client: TestClient) -> None:
    member_id = _invite(client)["member"]["id"]
    other = authenticate(client, organization="Other office", email="boss@other.example", set_header=False)
    headers = _as(client, other["token"])
    emails = {member["email"] for member in client.get("/team", headers=headers).json()}
    assert emails == {"boss@other.example"}
    assert client.patch(f"/team/{member_id}", json={"role": "owner"}, headers=headers).status_code == 404
    taken = client.post("/team/invite", json={"email": "noa@example.com", "display_name": "x"}, headers=headers)
    assert taken.status_code == 409 and taken.json()["code"] == "email_taken"


def test_resending_an_invite_replaces_the_old_link(client: TestClient) -> None:
    first = _invite(client)
    second = client.post(f"/team/{first['member']['id']}/resend-invite")
    assert second.status_code == 200, second.text
    with SignedOut(client) as anonymous:
        old = anonymous.post("/account/link", json={"token": _token(first["invite_url"], "join")})
        assert old.status_code == 410
        new = anonymous.post("/account/link", json={"token": _token(second.json()["invite_url"], "join")})
        assert new.status_code == 200


def test_an_expired_invite_shows_as_expired_and_does_not_work(client: TestClient) -> None:
    result = _invite(client)

    async def expire() -> None:
        async with session_scope() as session:
            await session.execute(update(AccountToken).values(expires_at=utcnow() - timedelta(minutes=1)))
            await session.commit()

    client.portal.call(expire)
    statuses = {member["email"]: member["status"] for member in client.get("/team").json()}
    assert statuses["noa@example.com"] == "invite_expired"
    with SignedOut(client) as anonymous:
        response = anonymous.post(
            "/account/invite/accept", json={"token": _token(result["invite_url"], "join"), "password": NEW_PASSWORD}
        )
    assert response.status_code == 410


def test_turning_an_account_off_signs_it_out_at_once(client: TestClient) -> None:
    token = _token(_invite(client)["invite_url"], "join")
    with SignedOut(client) as anonymous:
        anonymous.post("/account/invite/accept", json={"token": token, "password": NEW_PASSWORD})
    staff = _login(client, "noa@example.com", NEW_PASSWORD).json()["token"]
    member_id = next(m["id"] for m in client.get("/team").json() if m["email"] == "noa@example.com")

    off = client.patch(f"/team/{member_id}", json={"is_active": False})
    assert off.status_code == 200 and off.json()["status"] == "inactive"
    assert client.get("/auth/me", headers=_as(client, staff)).status_code == 401
    assert _login(client, "noa@example.com", NEW_PASSWORD).status_code == 401

    on = client.patch(f"/team/{member_id}", json={"is_active": True})
    assert on.json()["status"] == "active"
    assert _login(client, "noa@example.com", NEW_PASSWORD).status_code == 200


def test_the_office_always_keeps_one_active_owner(client: TestClient) -> None:
    me = client.get("/team").json()[0]["id"]
    demote = client.patch(f"/team/{me}", json={"role": "staff"})
    assert demote.status_code == 409 and demote.json()["code"] == "last_owner"
    off = client.patch(f"/team/{me}", json={"is_active": False})
    assert off.status_code == 400 and off.json()["code"] == "self_deactivate"

    second = _invite(client, email="partner@example.com", role="owner")["member"]["id"]
    # An owner who has not joined yet still counts; two owners let the first step down.
    assert client.patch(f"/team/{me}", json={"role": "staff"}).status_code == 200
    assert client.get("/auth/me").json()["role"] == "staff"
    assert client.patch(f"/team/{second}", json={"role": "staff"}).status_code == 403


def test_forgot_password_sends_a_link_that_sets_a_new_password(client: TestClient, tmp_path: Path) -> None:
    old_session = client.headers["Authorization"]
    with SignedOut(client) as anonymous:
        known = anonymous.post("/account/password/forgot", json={"email": "Staff@Example.com"})
        unknown = anonymous.post("/account/password/forgot", json={"email": "nobody@example.com"})
        assert known.status_code == unknown.status_code == 202
        assert known.json() == unknown.json()
        [mail] = _outbox(tmp_path)
        assert mail["To"] == "staff@example.com"
        url = re.search(r"https://office\.example/reset-password/\S+", mail.get_body(("plain",)).get_content()).group(0)
        token = _token(url, "reset-password")

        # A second request right away sends nothing new.
        anonymous.post("/account/password/forgot", json={"email": "staff@example.com"})
        assert len(_outbox(tmp_path)) == 1

        info = anonymous.post("/account/link", json={"token": token}).json()
        assert info["purpose"] == "reset" and info["email"] == "staff@example.com"
        # An invite link cannot be used as a reset link, and the other way round.
        wrong = anonymous.post("/account/invite/accept", json={"token": token, "password": NEW_PASSWORD})
        assert wrong.status_code == 410
        reset = anonymous.post("/account/password/reset", json={"token": token, "password": NEW_PASSWORD})
        assert reset.status_code == 204, reset.text
        assert anonymous.post("/account/password/reset", json={"token": token, "password": NEW_PASSWORD}).status_code == 410

    # Every device that was signed in is signed out.
    assert client.get("/auth/me", headers={"Authorization": old_session}).status_code == 401
    assert _login(client, "staff@example.com", PASSWORD).status_code == 401
    assert _login(client, "staff@example.com", NEW_PASSWORD).status_code == 200


def test_a_reset_also_clears_a_locked_account(client: TestClient) -> None:
    async def lock() -> None:
        async with session_scope() as session:
            await session.execute(
                update(User).values(failed_logins=99, locked_until=utcnow() + timedelta(hours=1))
            )
            await session.commit()

    client.portal.call(lock)
    with SignedOut(client) as anonymous:
        anonymous.post("/account/password/forgot", json={"email": "staff@example.com"})

    async def make_token() -> str:
        # The emailed token is not readable from the database, so swap in a known one.
        from app.services.team_service import _hash

        async with session_scope() as session:
            await session.execute(update(AccountToken).values(token_hash=_hash("known-token")))
            await session.commit()
        return "known-token"

    token = client.portal.call(make_token)
    with SignedOut(client) as anonymous:
        assert anonymous.post("/account/password/reset", json={"token": token, "password": NEW_PASSWORD}).status_code == 204
    assert _login(client, "staff@example.com", NEW_PASSWORD).status_code == 200


def test_account_links_share_the_login_rate_limit(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.rate_limit import reset

    monkeypatch.setenv("LOGIN_RATE_LIMIT", "3")
    get_settings.cache_clear()
    reset()  # The fixture's own login counted toward the same limit.
    with SignedOut(client) as anonymous:
        codes = [anonymous.post("/account/link", json={"token": f"guess-{n}"}).status_code for n in range(4)]
    assert codes[:3] == [410, 410, 410]
    assert codes[3] == 429


def test_signed_out_sessions_stay_revoked_after_deactivation(client: TestClient) -> None:
    """Deactivation writes revoked_at on the session rows, not only a flag on the user."""
    token = _token(_invite(client)["invite_url"], "join")
    with SignedOut(client) as anonymous:
        anonymous.post("/account/invite/accept", json={"token": token, "password": NEW_PASSWORD})
    _login(client, "noa@example.com", NEW_PASSWORD)
    member_id = next(m["id"] for m in client.get("/team").json() if m["email"] == "noa@example.com")
    client.patch(f"/team/{member_id}", json={"is_active": False})

    async def open_sessions() -> int:
        async with session_scope() as session:
            user = await session.scalar(select(User).where(User.email == "noa@example.com"))
            rows = await session.scalars(
                select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            )
            return len(list(rows))

    assert client.portal.call(open_sessions) == 0
