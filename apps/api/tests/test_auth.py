import ast
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.user import User
from app.models.user_session import UserSession
from tests.support import PASSWORD, api_routes, authenticate

_FAILURE = {"detail": "Email or password is incorrect.", "code": "unauthenticated"}
_DOCS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


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


def _public(path: str) -> bool:
    return path in {"/health", "/auth/login"} or path == "/portal" or path.startswith("/portal/") or path in _DOCS


def test_office_routes_require_a_session(client: TestClient) -> None:
    saved = client.headers.pop("Authorization")
    try:
        protected = {(method, path) for method, path in api_routes(client) if not _public(path)}
        assert {("GET", "/cases"), ("GET", "/processes"), ("POST", "/cases/{case_id}/fill-and-sign")} <= protected
        for method, path in sorted(protected):
            concrete = path.replace("{case_id}", str(uuid4())).replace("{document_id}", str(uuid4()))
            response = client.request(method, concrete)
            assert response.status_code == 401, f"{method} {path} -> {response.status_code} {response.text}"
    finally:
        client.headers["Authorization"] = saved


def test_password_hash_is_argon2_and_the_session_token_is_hashed(client: TestClient) -> None:
    token = client.headers["Authorization"].removeprefix("Bearer ")

    async def stored():
        async with session_scope() as session:
            user = await session.scalar(select(User).where(User.email == "staff@example.com"))
            record = await session.scalar(select(UserSession))
            assert user is not None and record is not None
            return user.password_hash, record.token_hash

    password_hash, token_hash = client.portal.call(stored)
    assert password_hash.startswith("$argon2")
    assert token not in token_hash
    assert token_hash == hashlib.sha256(token.encode()).hexdigest()


def test_login_failures_share_one_body(client: TestClient) -> None:
    saved = client.headers.pop("Authorization")
    try:
        wrong = client.post("/auth/login", json={"email": "staff@example.com", "password": "not-the-password"})
        unknown = client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
        assert wrong.status_code == 401
        assert wrong.json() == _FAILURE
        assert unknown.json() == _FAILURE

        async def deactivate() -> None:
            async with session_scope() as session:
                user = await session.scalar(select(User).where(User.email == "staff@example.com"))
                assert user is not None
                user.is_active = False
                await session.commit()

        client.portal.call(deactivate)
        inactive = client.post("/auth/login", json={"email": "staff@example.com", "password": PASSWORD})
        assert inactive.json() == _FAILURE
    finally:
        client.headers["Authorization"] = saved


def test_lock_after_configured_failures(client: TestClient) -> None:
    get_settings().login_max_failures = 2
    saved = client.headers.pop("Authorization")
    try:
        for _ in range(2):
            refused = client.post("/auth/login", json={"email": "staff@example.com", "password": "not-the-password"})
            assert refused.json() == _FAILURE
        locked = client.post("/auth/login", json={"email": "staff@example.com", "password": PASSWORD})
        assert locked.status_code == 401
        assert locked.json() == _FAILURE
    finally:
        client.headers["Authorization"] = saved


def test_expired_and_revoked_sessions_are_rejected(client: TestClient) -> None:
    token = client.headers["Authorization"].removeprefix("Bearer ")
    me = client.get("/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["organization_name"] == "Test office"

    async def expire() -> None:
        async with session_scope() as session:
            record = await session.scalar(
                select(UserSession).where(UserSession.token_hash == hashlib.sha256(token.encode()).hexdigest())
            )
            assert record is not None
            record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
            await session.commit()

    client.portal.call(expire)
    assert client.get("/auth/me").status_code == 401
    fresh = authenticate(client, set_header=True)
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/me").status_code == 401
    client.headers["Authorization"] = f"Bearer {fresh['token']}"
    assert client.get("/auth/me").status_code == 401


def test_session_and_signing_tokens_are_not_interchangeable(client: TestClient, tmp_path: Path) -> None:
    from tests.test_portal import _ready, _token

    case_id, _ = _ready(client, tmp_path)
    created = client.post(f"/cases/{case_id}/signing-links")
    assert created.status_code == 201, created.text
    signing = _token(created.json()["url"])
    office = client.headers["Authorization"]
    portal = client.get("/portal", headers={"Authorization": office})
    assert portal.status_code == 404
    cases = client.get("/cases", headers={"Authorization": f"Bearer {signing}"})
    assert cases.status_code == 401


def test_case_selection_is_centralized() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    select_allowed = {(root / "domain" / "case_scope.py").resolve(), (root / "db" / "compat.py").resolve()}
    system_allowed = {
        (root / "domain" / "case_scope.py").resolve(),
        (root / "workers" / "runner.py").resolve(),
        (root / "core" / "deps.py").resolve(),
        (root / "services" / "storage_migration.py").resolve(),
    }
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name in {"select", "get"} and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "Case":
                assert path.resolve() in select_allowed, path
            if (
                name == "system"
                and isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "CaseScope"
            ):
                assert path.resolve() in system_allowed, path
