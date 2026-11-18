"""Claude as the main model, Gemini as the backup: what each call sends, and who answers when."""

import asyncio
from types import SimpleNamespace

import pytest

from app.core.config import Settings, get_settings
from app.core.container import build_container
from app.domain.classification import DocumentClassification, FieldExtraction, FieldHit
from app.schemas.process import FieldSpec
from app.services.claude_client import FALLBACK_BETA, ClaudeClient
from app.services.document_processor import PageImage
from app.services.gemini_client import GeminiUnavailable
from app.services.model_router import RoutedModelClient

_PAGE = PageImage(mime_type="image/png", data=b"\x89PNG fake")
_CLASSIFIED = DocumentClassification(document_type="id_copy", confidence=0.93, language="he")


class _Stream:
    def __init__(self, chunks: list[str], fail_after: int | None = None) -> None:
        self._chunks = chunks
        self._fail_after = fail_after

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    @property
    def text_stream(self):
        async def chunks():
            for index, chunk in enumerate(self._chunks):
                if self._fail_after is not None and index == self._fail_after:
                    raise RuntimeError("stream broke")
                yield chunk

        return chunks()


class _FakeMessages:
    """Stands in for `AsyncAnthropic().beta.messages` and keeps every request it gets."""

    def __init__(self, parsed=None, stop_reason: str = "end_turn", text: str = "", chunks=None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._parsed = parsed
        self._stop_reason = stop_reason
        self._text = text
        self._chunks = chunks or []

    async def parse(self, **kwargs):
        self.calls.append(("parse", kwargs))
        return SimpleNamespace(stop_reason=self._stop_reason, parsed_output=self._parsed)

    async def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return SimpleNamespace(
            stop_reason=self._stop_reason,
            content=[SimpleNamespace(type="text", text=self._text)],
        )

    def stream(self, **kwargs):
        self.calls.append(("stream", kwargs))
        return _Stream(self._chunks)


def _claude(messages: _FakeMessages, key: str = "test-key") -> ClaudeClient:
    client = ClaudeClient(Settings(anthropic_api_key=key, gemini_api_key=""))
    client._sdk = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    return client


def _assert_claude_request(kwargs: dict, effort: str = "low") -> None:
    assert kwargs["model"] == "claude-opus-5-5"
    assert kwargs["betas"] == [FALLBACK_BETA]
    assert kwargs["fallbacks"] == "default"
    assert kwargs["output_config"] == {"effort": effort}
    # Thinking is always on for this model; sending a thinking setting would be rejected.
    assert "thinking" not in kwargs and "temperature" not in kwargs


class _FakeProvider:
    def __init__(self, name: str, configured: bool = True, fail: bool = False, text: str = "", chunks=None, fail_after=None):
        self.name = name
        self.configured = configured
        self.fail = fail
        self.text = text
        self.chunks = chunks or []
        self.fail_after = fail_after
        self.calls: list[str] = []

    async def classify_document(self, *, system, prompt, images):
        self.calls.append("classify")
        if self.fail:
            raise RuntimeError(f"{self.name} is down")
        return _CLASSIFIED.model_copy(update={"summary": self.name})

    async def extract_fields(self, *, message, fields):
        self.calls.append("extract")
        if self.fail:
            raise GeminiUnavailable(f"{self.name} is down")
        return FieldExtraction(fields=[FieldHit(key="phone", value=self.name)])

    async def transcribe(self, images):
        self.calls.append("transcribe")
        return self.text

    async def stream_text(self, *, system, prompt):
        self.calls.append("stream")
        for index, chunk in enumerate(self.chunks):
            if self.fail_after is not None and index == self.fail_after:
                raise RuntimeError(f"{self.name} broke")
            yield chunk
        if self.fail and not self.chunks:
            raise RuntimeError(f"{self.name} is down")

    async def embed(self, text):
        self.calls.append("embed")
        return [0.1, 0.2]


async def _collect(stream) -> list[str]:
    return [chunk async for chunk in stream]


# The Claude client


def test_claude_reads_a_document_with_the_pages_first_and_a_typed_answer() -> None:
    messages = _FakeMessages(parsed=_CLASSIFIED)
    result = asyncio.run(_claude(messages).classify_document(system="Sort this.", prompt="Which drawer?", images=[_PAGE]))
    assert result == _CLASSIFIED
    [(kind, kwargs)] = messages.calls
    assert kind == "parse"
    _assert_claude_request(kwargs)
    assert kwargs["system"] == "Sort this."
    assert kwargs["output_format"] is DocumentClassification
    content = kwargs["messages"][0]["content"]
    assert [block["type"] for block in content] == ["image", "text"]
    assert content[0]["source"] == {"type": "base64", "media_type": "image/png", "data": "iVBORyBmYWtl"}
    assert content[1]["text"] == "Which drawer?"


def test_claude_fills_fields_and_a_declined_answer_is_not_trusted() -> None:
    fields = [FieldSpec(key="phone", label="Phone", field_type="phone", pdf_field_name="phone")]
    found = FieldExtraction(fields=[FieldHit(key="phone", value="0501234567")])
    messages = _FakeMessages(parsed=found)
    assert asyncio.run(_claude(messages).extract_fields(message="my phone is 0501234567", fields=fields)) == found
    [(_kind, kwargs)] = messages.calls
    _assert_claude_request(kwargs)
    assert kwargs["output_format"] is FieldExtraction
    assert "- key phone (phone): Phone" in kwargs["messages"][0]["content"]

    declined = _FakeMessages(parsed=None, stop_reason="refusal")
    with pytest.raises(GeminiUnavailable):
        asyncio.run(_claude(declined).extract_fields(message="x", fields=fields))


def test_claude_transcribes_streams_and_has_no_embeddings() -> None:
    messages = _FakeMessages(text="  שם פרטי: דנה\n", chunks=["שלום", " דנה"])
    client = _claude(messages)
    assert asyncio.run(client.transcribe([_PAGE])) == "שם פרטי: דנה"
    assert asyncio.run(_collect(client.stream_text(system="Be brief.", prompt="hi"))) == ["שלום", " דנה"]
    kinds = [kind for kind, _ in messages.calls]
    assert kinds == ["create", "stream"]
    for _kind, kwargs in messages.calls:
        _assert_claude_request(kwargs)
    with pytest.raises(GeminiUnavailable):
        asyncio.run(client.embed("text"))

    # A declined page reads as empty, never as the refusal text.
    assert asyncio.run(_claude(_FakeMessages(text="I can't", stop_reason="refusal")).transcribe([_PAGE])) == ""


def test_claude_without_a_key_makes_no_call() -> None:
    client = ClaudeClient(Settings(anthropic_api_key="", gemini_api_key=""))
    assert client.configured is False
    assert asyncio.run(client.transcribe([_PAGE])) == ""
    with pytest.raises(GeminiUnavailable):
        asyncio.run(client.classify_document(system="", prompt="", images=[]))


# The router


def test_the_main_model_answers_and_the_backup_takes_over_when_it_fails() -> None:
    claude, gemini = _FakeProvider("claude"), _FakeProvider("gemini")
    router = RoutedModelClient(claude, gemini, embedder=gemini)
    assert asyncio.run(router.classify_document(system="", prompt="", images=[])).summary == "claude"
    assert gemini.calls == []

    down = _FakeProvider("claude", fail=True)
    router = RoutedModelClient(down, gemini, embedder=gemini)
    assert asyncio.run(router.classify_document(system="", prompt="", images=[])).summary == "gemini"
    assert asyncio.run(router.extract_fields(message="", fields=[])).fields[0].value == "gemini"
    assert down.calls == ["classify", "extract"]

    # Without a key the main model is skipped, not tried.
    unset = _FakeProvider("claude", configured=False)
    router = RoutedModelClient(unset, gemini, embedder=gemini)
    assert asyncio.run(router.extract_fields(message="", fields=[])).fields[0].value == "gemini"
    assert unset.calls == []

    # When both fail, the last failure is what the caller sees.
    both = RoutedModelClient(_FakeProvider("claude", fail=True), _FakeProvider("gemini", fail=True), embedder=gemini)
    with pytest.raises(GeminiUnavailable):
        asyncio.run(both.extract_fields(message="", fields=[]))
    none = RoutedModelClient(_FakeProvider("c", configured=False), _FakeProvider("g", configured=False), embedder=gemini)
    assert none.configured is False
    with pytest.raises(GeminiUnavailable):
        asyncio.run(none.classify_document(system="", prompt="", images=[]))


def test_streaming_switches_only_before_the_first_word() -> None:
    gemini = _FakeProvider("gemini", chunks=["g1", "g2"])
    silent = _FakeProvider("claude", fail=True)
    router = RoutedModelClient(silent, gemini, embedder=gemini)
    assert asyncio.run(_collect(router.stream_text(system="", prompt=""))) == ["g1", "g2"]

    broken = _FakeProvider("claude", chunks=["c1", "c2"], fail_after=1)
    router = RoutedModelClient(broken, _FakeProvider("gemini", chunks=["g1"]), embedder=gemini)
    seen: list[str] = []

    async def read() -> None:
        async for chunk in router.stream_text(system="", prompt=""):
            seen.append(chunk)

    with pytest.raises(RuntimeError):
        asyncio.run(read())
    assert seen == ["c1"]


def test_an_empty_page_goes_to_the_backup_and_embeddings_stay_with_gemini() -> None:
    claude, gemini = _FakeProvider("claude", text=""), _FakeProvider("gemini", text="lines")
    router = RoutedModelClient(claude, gemini, embedder=gemini)
    assert asyncio.run(router.transcribe([_PAGE])) == "lines"
    assert asyncio.run(router.embed("text")) == [0.1, 0.2]
    assert "embed" not in claude.calls


# Wiring


def test_claude_is_the_main_model_unless_the_office_chooses_gemini() -> None:
    container = build_container(Settings(anthropic_api_key="k", gemini_api_key="g"))
    assert type(container.model.primary).__name__ == "ClaudeClient"
    assert type(container.model.backup).__name__ == "GoogleGeminiClient"
    assert container.settings.claude_model == "claude-opus-5-5"
    assert container.chat._gemini is container.model

    flipped = build_container(Settings(anthropic_api_key="k", gemini_api_key="g", ai_provider="gemini"))
    assert type(flipped.model.primary).__name__ == "GoogleGeminiClient"


def test_tests_never_see_a_real_anthropic_key() -> None:
    get_settings.cache_clear()
    try:
        assert get_settings().anthropic_api_key == ""
    finally:
        get_settings.cache_clear()
