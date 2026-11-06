import asyncio
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from app.db.session import session_scope
from app.domain.classification import FieldExtraction, FieldHit
from app.schemas.chat import ChatRequest
from app.services.case_service import CaseService


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("TEMPLATE_DIR", str(tmp_path / "templates"))
    monkeypatch.setenv("QUEUE_ENABLED", "false")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("QDRANT_URL", "")
    monkeypatch.setenv("AUTO_CREATE_SCHEMA", "true")
    from app.core.config import get_settings
    from app.db.session import reset_db

    get_settings.cache_clear()
    reset_db()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    reset_db()
    get_settings.cache_clear()


def _case(client: TestClient) -> str:
    created = client.post(
        "/cases",
        json={"name": "Dana Cohen", "process_key": "onboarding", "client_name": "Dana"},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _events(body: str) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for block in body.split("\n\n"):
        if not block.strip() or block.startswith(":"):
            continue
        event = ""
        data: list[str] = []
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data.append(line[5:].strip())
        found.append((event, "\n".join(data)))
    return found


def test_unconfigured_stream_sends_the_recorded_reply(client: TestClient) -> None:
    case_id = _case(client)
    response = client.post(f"/cases/{case_id}/chat/stream", json={"message": "Dana Cohen"})
    assert response.status_code == 200, response.text
    events = _events(response.text)
    deltas = [json.loads(data) for event, data in events if event == "delta"]
    assert len(deltas) == 1
    assert events[-1][0] == "workspace"
    workspace = json.loads(events[-1][1])
    assert workspace["messages"][-1]["content"] == deltas[0]


def test_stream_tokens_replace_the_stored_reply(client: TestClient) -> None:
    case_id = _case(client)
    prompts: list[str] = []

    class Fake:
        configured = True

        async def extract_fields(self, *, message: str, fields: list) -> FieldExtraction:
            return FieldExtraction(fields=[FieldHit(key="full_name", value=message)])

        async def stream_text(self, *, system: str, prompt: str):
            prompts.append(prompt)
            yield "Rec"
            yield "orded"

    client.app.state.container.chat._gemini = Fake()
    response = client.post(f"/cases/{case_id}/chat/stream", json={"message": "Dana Cohen"})
    assert response.status_code == 200, response.text
    events = [(event, json.loads(data)) for event, data in _events(response.text)]
    assert [event for event, _ in events[:2]] == ["delta", "delta"]
    assert [data for event, data in events if event == "delta"] == ["Rec", "orded"]
    assert events[-1][0] == "workspace"
    assert events[-1][1]["messages"][-1]["content"] == "Recorded"
    assert prompts
    assert "Dana Cohen" not in prompts[0]


def test_stream_error_replaces_partial_text_with_the_recorded_reply(client: TestClient) -> None:
    case_id = _case(client)

    class Fake:
        configured = True

        async def extract_fields(self, *, message: str, fields: list) -> FieldExtraction:
            return FieldExtraction(fields=[])

        async def stream_text(self, *, system: str, prompt: str):
            yield "Hello"
            raise RuntimeError("stopped")

    client.app.state.container.chat._gemini = Fake()
    response = client.post(f"/cases/{case_id}/chat/stream", json={"message": "Dana Cohen"})
    assert response.status_code == 200, response.text
    events = _events(response.text)
    replaced = [json.loads(data) for event, data in events if event == "replace"]
    assert len(replaced) == 1
    workspace = json.loads(events[-1][1])
    assert workspace["messages"][-1]["content"] == replaced[0]
    assert replaced[0] != "Hello"


def test_idle_timeout_falls_back_to_a_workspace(client: TestClient) -> None:
    case_id = _case(client)
    client.app.state.container.settings.chat_stream_idle_timeout_seconds = 0.05

    class Fake:
        configured = True

        async def extract_fields(self, *, message: str, fields: list) -> FieldExtraction:
            return FieldExtraction(fields=[])

        async def stream_text(self, *, system: str, prompt: str):
            await asyncio.sleep(30)
            yield "late"

    client.app.state.container.chat._gemini = Fake()
    response = client.post(f"/cases/{case_id}/chat/stream", json={"message": "Dana Cohen"})
    assert response.status_code == 200, response.text
    events = _events(response.text)
    assert events[-1][0] == "workspace"


def test_unknown_case_is_a_real_404(client: TestClient) -> None:
    response = client.post(f"/cases/{uuid4()}/chat/stream", json={"message": "Dana Cohen"})
    assert response.status_code == 404
    assert "event: workspace" not in response.text


def test_chat_begin_stores_the_user_message_and_recorded_reply(client: TestClient) -> None:
    case_id = _case(client)

    async def begin():
        async with session_scope() as session:
            return await CaseService(session, client.app.state.container).chat_begin(
                UUID(case_id),
                ChatRequest(message="Dana Cohen"),
            )

    start = client.portal.call(begin)
    workspace = client.get(f"/cases/{case_id}")
    assert workspace.status_code == 200
    contents = [item["content"] for item in workspace.json()["messages"]]
    assert "Dana Cohen" in contents
    assert start.turn.reply in contents
