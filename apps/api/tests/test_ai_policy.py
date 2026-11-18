"""An office can turn AI reading off: then nothing of that office reaches a model."""

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("fitz")
pytest.importorskip("aiosqlite")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from app.domain.ai_policy import ai_allowed, set_ai_allowed
from app.domain.classification import DocumentClassification, FieldExtraction, FieldHit
from app.services.gemini_client import GeminiUnavailable
from app.services.model_router import RoutedModelClient
from tests.support import SignedOut, authenticate
from tests.test_bl6101_sanity_drill import _pdf
from tests.test_smart_upload_and_real_estate import client  # noqa: F401  (the fixture)


class _CountingModel:
    """A configured model that answers everything and remembers every call it got."""

    configured = True

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def classify_document(self, *, system, prompt, images):
        self.calls.append("classify")
        return DocumentClassification(document_type="id_copy", confidence=0.97, language="he")

    async def extract_fields(self, *, message, fields):
        self.calls.append("extract")
        return FieldExtraction(fields=[FieldHit(key="phone", value="0501234567")])

    async def transcribe(self, images):
        self.calls.append("transcribe")
        return "text"

    async def stream_text(self, *, system, prompt):
        self.calls.append("stream")
        yield "ok"

    async def embed(self, text):
        self.calls.append("embed")
        return [0.1]


def _install(client: TestClient) -> _CountingModel:
    """Every model call of the running app goes to one counting model."""
    model = _CountingModel()
    router = client.app.state.container.model
    router.primary, router.backup, router._embedder = model, model, model
    return model


def _ai(client: TestClient, enabled: bool, headers: dict[str, str] | None = None) -> dict:
    changed = client.put("/organization/ai-reading", headers=headers, json={"enabled": enabled})
    assert changed.status_code == 200, changed.text
    return changed.json()


def _open(client: TestClient, headers: dict[str, str] | None = None) -> str:
    created = client.post("/cases", headers=headers, json={"name": "Case", "process_key": "bl_6101", "client_name": "דנה"})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _upload(client: TestClient, case_id: str, tmp_path: Path, headers: dict[str, str] | None = None) -> dict:
    uploaded = client.post(
        f"/cases/{case_id}/upload",
        headers=headers,
        files=[("files", ("scan.pdf", _pdf(tmp_path / "scan.pdf", ["מסמך סרוק"]), "application/pdf"))],
    )
    assert uploaded.status_code == 200, uploaded.text
    return client.get(f"/cases/{case_id}", headers=headers).json()


def test_the_router_sends_nothing_when_the_office_said_no() -> None:
    model = _CountingModel()
    router = RoutedModelClient(model, model, embedder=model)

    async def blocked() -> tuple:
        set_ai_allowed(False)
        with pytest.raises(GeminiUnavailable, match="off for this office"):
            await router.classify_document(system="", prompt="", images=[])
        with pytest.raises(GeminiUnavailable):
            await router.extract_fields(message="", fields=[])
        with pytest.raises(GeminiUnavailable):
            await router.embed("text")
        with pytest.raises(GeminiUnavailable):
            [chunk async for chunk in router.stream_text(system="", prompt="")]
        return router.configured, await router.transcribe([])

    assert asyncio.run(blocked()) == (False, "")
    assert model.calls == []

    # The answer belongs to the task that set it: other work is not affected.
    assert ai_allowed() is True
    assert asyncio.run(router.classify_document(system="", prompt="", images=[])).document_type == "id_copy"
    assert model.calls == ["classify"]


def test_an_office_turns_ai_reading_off_and_on(client: TestClient) -> None:
    assert client.get("/organization").json()["ai_reading_enabled"] is True
    assert _ai(client, False)["ai_reading_enabled"] is False
    assert client.get("/organization").json()["ai_reading_enabled"] is False
    assert _ai(client, False)["ai_reading_enabled"] is False

    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    assert client.get("/organization", headers=headers).json()["ai_reading_enabled"] is True
    assert client.put("/organization/ai-reading", json={"enabled": "maybe"}).status_code == 422
    with SignedOut(client) as anonymous:
        assert anonymous.request("PUT", "/organization/ai-reading", json={"enabled": True}).status_code == 401
    assert _ai(client, True)["ai_reading_enabled"] is True


def test_with_ai_off_documents_and_chat_never_reach_a_model(client: TestClient, tmp_path: Path) -> None:
    model = _install(client)

    # On: the uploaded scan is sorted by the model, and the chat asks it for values.
    on_case = _open(client)
    body = _upload(client, on_case, tmp_path)
    assert "classify" in model.calls
    assert [item["document_type"] for item in body["gap"]["identified"]] == ["id_copy"]
    assert client.post(f"/cases/{on_case}/chat", json={"message": "הטלפון שלי 0501234567"}).status_code == 200
    assert "extract" in model.calls

    # Off: the same work sends nothing. The file waits for the office to sort it.
    _ai(client, False)
    model.calls.clear()
    off_case = _open(client)
    body = _upload(client, off_case, tmp_path)
    assert body["gap"]["identified"] == []
    assert [item["filename"] for item in body["gap"]["unrecognized"]] == ["scan.pdf"]
    chatted = client.post(f"/cases/{off_case}/chat", json={"message": "הטלפון שלי 0501234567"})
    assert chatted.status_code == 200, chatted.text
    streamed = client.post(f"/cases/{off_case}/chat/stream", json={"message": "שלום"})
    assert streamed.status_code == 200
    assert model.calls == []

    # Another office, with AI on, is still read by the model in the same running server.
    other = authenticate(client, organization="Other office", email="other@example.com", set_header=False)
    headers = {"Authorization": f"Bearer {other['token']}"}
    other_case = _open(client, headers=headers)
    _upload(client, other_case, tmp_path, headers=headers)
    assert model.calls == ["classify"]
