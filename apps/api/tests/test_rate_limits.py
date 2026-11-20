from pathlib import Path

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.rate_limit import LoginThrottle, SlidingWindow
from tests.support import PASSWORD, authenticate

_FAILURE = {"detail": "Email or password is incorrect.", "code": "unauthenticated"}
_HASH = "0" * 64


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


def _login(client: TestClient, ip: str, password: str = PASSWORD):
    return client.post(
        "/auth/login",
        json={"email": "staff@example.com", "password": password},
        headers={"Authorization": "", "X-Client-Ip": ip},
    )


def test_wrong_passwords_lock_out_the_address_not_the_colleague(client: TestClient) -> None:
    get_settings().login_max_failures = 2
    for _ in range(2):
        assert _login(client, "203.0.113.5", "not-the-password").json() == _FAILURE
    # The guesser's address stays out, even with the right password.
    assert _login(client, "203.0.113.5").json() == _FAILURE
    # The staff member at the office signs in as usual.
    assert _login(client, "198.51.100.7").status_code == 200


def test_the_account_locks_after_many_failures_from_anywhere(client: TestClient) -> None:
    settings = get_settings()
    settings.login_max_failures = 10
    settings.login_account_max_failures = 3
    for ip in ("203.0.113.1", "203.0.113.2", "203.0.113.3"):
        assert _login(client, ip, "not-the-password").json() == _FAILURE
    assert _login(client, "198.51.100.7").json() == _FAILURE


def test_a_right_password_clears_the_address_count(client: TestClient) -> None:
    get_settings().login_max_failures = 2
    assert _login(client, "203.0.113.5", "not-the-password").status_code == 401
    assert _login(client, "203.0.113.5").status_code == 200
    assert _login(client, "203.0.113.5", "not-the-password").status_code == 401
    assert _login(client, "203.0.113.5").status_code == 200


def test_login_attempts_are_limited_per_address(client: TestClient) -> None:
    get_settings().login_rate_limit = 3
    for _ in range(3):
        assert _login(client, "203.0.113.9", "not-the-password").status_code == 401
    refused = _login(client, "203.0.113.9")
    assert refused.status_code == 429
    assert refused.json()["code"] == "rate_limited"
    assert int(refused.headers["Retry-After"]) >= 1
    # Another address is unaffected.
    assert _login(client, "198.51.100.7").status_code == 200


def test_public_routes_are_limited_and_office_routes_are_not(client: TestClient) -> None:
    get_settings().public_rate_limit = 2
    headers = {"X-Client-Ip": "203.0.113.20"}
    for _ in range(2):
        assert client.get(f"/verify/by-hash/{_HASH}", headers=headers).status_code != 429
    assert client.get(f"/verify/by-hash/{_HASH}", headers=headers).status_code == 429
    assert client.get("/portal/state", headers=headers).status_code == 429
    assert client.get(f"/verify/by-hash/{_HASH}", headers={"X-Client-Ip": "198.51.100.8"}).status_code != 429
    for _ in range(5):
        assert client.get("/cases", headers=headers).status_code == 200


def test_the_limits_can_be_switched_off(client: TestClient) -> None:
    settings = get_settings()
    settings.public_rate_limit = 1
    settings.rate_limit_enabled = False
    for _ in range(3):
        assert client.get(f"/verify/by-hash/{_HASH}").status_code != 429


def test_a_spoofed_address_header_that_is_not_an_address_is_ignored(client: TestClient) -> None:
    get_settings().public_rate_limit = 1
    assert client.get(f"/verify/by-hash/{_HASH}", headers={"X-Client-Ip": "not-an-ip"}).status_code != 429
    # Falls back to the connection's own address, which the next garbage header shares.
    assert client.get(f"/verify/by-hash/{_HASH}", headers={"X-Client-Ip": "also-not"}).status_code == 429


def test_sliding_window_forgets_old_hits() -> None:
    now = [0.0]
    window = SlidingWindow(clock=lambda: now[0])
    assert window.hit("k", 2, 10) is None
    assert window.hit("k", 2, 10) is None
    assert window.hit("k", 2, 10) == pytest.approx(10.0)
    now[0] = 10.5
    assert window.hit("k", 2, 10) is None


def test_login_lock_ends_after_its_time() -> None:
    now = [0.0]
    throttle = LoginThrottle(clock=lambda: now[0])
    throttle.fail("a@b.c", "1.2.3.4", 2, 60)
    throttle.fail("a@b.c", "1.2.3.4", 2, 60)
    assert throttle.locked("a@b.c", "1.2.3.4")
    assert not throttle.locked("a@b.c", "5.6.7.8")
    now[0] = 61
    assert not throttle.locked("a@b.c", "1.2.3.4")
