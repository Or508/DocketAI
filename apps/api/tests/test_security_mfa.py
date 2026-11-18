"""A staff member's own security: changing the password, and two-step login with an authenticator app."""

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.db.compat import _add_missing_case_columns
from app.domain import totp
from tests.support import PASSWORD, SignedOut
from tests.test_smart_upload_and_real_estate import client  # noqa: F401  (the fixture)

_EMAIL = "staff@example.com"
_NEW_PASSWORD = "a-much-longer-passphrase-2026"
# RFC 6238, appendix B: the ASCII secret "12345678901234567890", SHA-1.
_RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def _login(client: TestClient, password: str = PASSWORD, code: str | None = None):
    body = {"email": _EMAIL, "password": password}
    if code is not None:
        body["code"] = code
    with SignedOut(client) as anonymous:
        return anonymous.post("/auth/login", json=body)


def _as(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _db_row(tmp_path: Path, column: str):
    connection = sqlite3.connect(tmp_path / "test.db")
    try:
        return connection.execute(f"SELECT {column} FROM users WHERE email = ?", (_EMAIL,)).fetchone()[0]
    finally:
        connection.close()


# The code generator


def test_codes_match_the_rfc_and_are_never_accepted_twice() -> None:
    assert totp.code_at(_RFC_SECRET, 59 // 30) == "287082"
    assert totp.code_at(_RFC_SECRET, 1111111109 // 30) == "081804"
    assert totp.code_at(_RFC_SECRET, 2000000000 // 30) == "279037"

    now = 1111111109.0
    step = totp.current_step(now)
    code = totp.code_at(_RFC_SECRET, step)
    assert totp.verify(_RFC_SECRET, code, now=now) == step
    assert totp.verify(_RFC_SECRET, f" {code[:3]} {code[3:]} ", now=now) == step
    # One step of clock drift either way is fine; two is not.
    assert totp.verify(_RFC_SECRET, totp.code_at(_RFC_SECRET, step - 1), now=now) == step - 1
    assert totp.verify(_RFC_SECRET, totp.code_at(_RFC_SECRET, step + 1), now=now) == step + 1
    assert totp.verify(_RFC_SECRET, totp.code_at(_RFC_SECRET, step - 2), now=now) is None
    # A code already used, or an older one, is refused.
    assert totp.verify(_RFC_SECRET, code, last_step=step, now=now) is None
    assert totp.verify(_RFC_SECRET, totp.code_at(_RFC_SECRET, step - 1), last_step=step - 1, now=now) is None
    for bad in ("", "12345", "1234567", "abcdef"):
        assert totp.verify(_RFC_SECRET, bad, now=now) is None

    secret = totp.new_secret()
    assert len(secret) == 32 and secret.isalnum()
    uri = totp.provisioning_uri(secret, account="staff@example.com", issuer="DocketFlow")
    assert uri.startswith("otpauth://totp/DocketFlow%3Astaff%40example.com?")
    assert f"secret={secret}" in uri and "issuer=DocketFlow" in uri and "digits=6" in uri and "period=30" in uri


# Password


def test_changing_the_password_signs_out_every_other_device(client: TestClient) -> None:
    other_device = _login(client).json()["token"]
    assert client.get("/auth/me", headers=_as(other_device)).status_code == 200

    wrong = client.post("/auth/password", json={"current_password": "not-it", "new_password": _NEW_PASSWORD})
    # A wrong typed password is a 400: the session itself is fine and must not be signed out.
    assert (wrong.status_code, wrong.json()["code"]) == (400, "wrong_password")
    assert client.get("/auth/me").status_code == 200
    short = client.post("/auth/password", json={"current_password": PASSWORD, "new_password": "short"})
    assert (short.status_code, short.json()["code"]) == (400, "weak_password")
    same = client.post("/auth/password", json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert (same.status_code, same.json()["code"]) == (400, "same_password")
    assert client.get("/auth/me", headers=_as(other_device)).status_code == 200

    changed = client.post("/auth/password", json={"current_password": PASSWORD, "new_password": _NEW_PASSWORD})
    assert changed.status_code == 204, changed.text
    # This device stays signed in; the other one is out.
    assert client.get("/auth/me").status_code == 200
    assert client.get("/auth/me", headers=_as(other_device)).status_code == 401
    assert _login(client).status_code == 401
    assert _login(client, _NEW_PASSWORD).status_code == 200


# Two-step login


def test_two_step_login_from_setup_to_switching_it_off(client: TestClient, tmp_path: Path) -> None:
    assert client.get("/auth/security").json() == {"mfa_enabled": False, "recovery_codes_left": 0, "min_password_length": 12}

    setup = client.post("/auth/mfa/setup")
    assert setup.status_code == 200, setup.text
    secret = setup.json()["secret"]
    assert setup.json()["otpauth_uri"].startswith("otpauth://totp/DocketFlow%3Astaff%40example.com?")
    # Not on until a code from the app confirms the secret.
    assert _login(client).status_code == 200

    wrong = client.post("/auth/mfa/enable", json={"code": "000000"})
    assert (wrong.status_code, wrong.json()["code"]) == (400, "mfa_invalid_code")
    step = totp.current_step()
    enabled = client.post("/auth/mfa/enable", json={"code": totp.code_at(secret, step)})
    assert enabled.status_code == 200, enabled.text
    recovery = enabled.json()["recovery_codes"]
    assert len(recovery) == 8 and len(set(recovery)) == 8 and all(len(code) == 9 and code[4] == "-" for code in recovery)
    assert client.get("/auth/security").json()["mfa_enabled"] is True
    assert client.get("/auth/security").json()["recovery_codes_left"] == 8

    # What the database holds: an encrypted secret and hashes, never the secret or a code.
    stored = _db_row(tmp_path, "mfa_secret")
    assert stored and secret not in stored
    hashes = _db_row(tmp_path, "mfa_recovery_hashes")
    assert all(code not in hashes for code in recovery)
    assert (tmp_path / "mfa.key").is_file()

    # The password alone is not enough any more, and says so.
    needed = _login(client)
    assert (needed.status_code, needed.json()["code"]) == (401, "mfa_required")
    bad = _login(client, code="000000")
    assert (bad.status_code, bad.json()["code"]) == (401, "mfa_required")
    # The code used to switch it on cannot sign in; the next one can, once.
    assert _login(client, code=totp.code_at(secret, step)).status_code == 401
    fresh = totp.code_at(secret, step + 1)
    assert _login(client, code=fresh).status_code == 200
    assert _login(client, code=fresh).status_code == 401
    # A wrong password with a right code still fails, without saying a code is needed.
    wrong_password = _login(client, password="not-it", code=totp.code_at(secret, step + 1))
    assert wrong_password.json()["code"] == "unauthenticated"

    # A recovery code signs in once.
    assert _login(client, code=recovery[0].upper()).status_code == 200
    assert _login(client, code=recovery[0]).status_code == 401
    assert client.get("/auth/security").json()["recovery_codes_left"] == 7

    on_already = client.post("/auth/mfa/setup")
    assert (on_already.status_code, on_already.json()["code"]) == (409, "mfa_already_on")
    renewed = client.post("/auth/mfa/recovery-codes", json={"password": PASSWORD, "code": recovery[1]})
    assert renewed.status_code == 200, renewed.text
    assert _login(client, code=recovery[2]).status_code == 401
    assert client.get("/auth/security").json()["recovery_codes_left"] == 8

    wrong_password = client.post("/auth/mfa/disable", json={"password": "not-it", "code": renewed.json()["recovery_codes"][0]})
    assert (wrong_password.status_code, wrong_password.json()["code"]) == (400, "wrong_password")
    off = client.post("/auth/mfa/disable", json={"password": PASSWORD, "code": renewed.json()["recovery_codes"][0]})
    assert off.status_code == 204, off.text
    assert client.get("/auth/security").json() == {"mfa_enabled": False, "recovery_codes_left": 0, "min_password_length": 12}
    assert _login(client).status_code == 200
    assert _db_row(tmp_path, "mfa_secret") is None
    off_already = client.post("/auth/mfa/disable", json={"password": PASSWORD, "code": "000000"})
    assert (off_already.status_code, off_already.json()["code"]) == (409, "mfa_not_on")


def test_wrong_codes_lock_the_account_like_wrong_passwords(client: TestClient) -> None:
    secret = client.post("/auth/mfa/setup").json()["secret"]
    assert client.post("/auth/mfa/enable", json={"code": totp.code_at(secret, totp.current_step())}).status_code == 200
    for _ in range(5):
        assert _login(client, code="000000").status_code == 401
    # Locked: even a right code is refused for now.
    locked = _login(client, code=totp.code_at(secret, totp.current_step() + 1))
    assert locked.status_code == 401


def test_no_security_route_answers_without_a_session(client: TestClient) -> None:
    with SignedOut(client) as anonymous:
        assert anonymous.get("/auth/security").status_code == 401
        for path in ("/auth/password", "/auth/mfa/setup", "/auth/mfa/enable", "/auth/mfa/disable", "/auth/mfa/recovery-codes"):
            assert anonymous.post(path, json={}).status_code == 401, path


def test_a_user_table_from_before_two_step_login_gets_its_columns(tmp_path: Path) -> None:
    database = tmp_path / "old.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE users (id CHAR(32) PRIMARY KEY, email VARCHAR(320))")
    connection.execute("INSERT INTO users (id, email) VALUES ('a', 'old@example.com')")
    connection.commit()
    connection.close()
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as sync_conn:
        _add_missing_case_columns(sync_conn)
        _add_missing_case_columns(sync_conn)
    with engine.connect() as sync_conn:
        columns = {column["name"] for column in inspect(sync_conn).get_columns("users")}
    engine.dispose()
    assert {"mfa_enabled", "mfa_secret", "mfa_pending_secret", "mfa_last_step", "mfa_recovery_hashes"} <= columns
    connection = sqlite3.connect(database)
    assert connection.execute("SELECT mfa_enabled FROM users").fetchall() == [(0,)]
    connection.close()
