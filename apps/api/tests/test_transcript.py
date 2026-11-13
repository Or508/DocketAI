"""A page without a text layer is stored as its raw transcript. Text read from the file wins."""

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("fitz")

from app.services.document_processor import ExtractionResult, PageImage
from app.services.gemini_client import GoogleGeminiClient
from app.services.pipeline import stored_text

_IMAGE = PageImage("image/jpeg", b"not-a-real-image")


class _Transcriber:
    def __init__(self, transcript: str) -> None:
        self.transcript = transcript
        self.calls = 0

    async def transcribe(self, images: list[PageImage]) -> str:
        self.calls += 1
        return self.transcript


def _extraction(text: str, images: list[PageImage]) -> ExtractionResult:
    return ExtractionResult(page_count=1, text=text, images=images, searchable=not images)


def _stored(text: str, images: list[PageImage], transcriber: _Transcriber | None) -> str:
    return asyncio.run(stored_text(_extraction(text, images), transcriber))


def test_text_read_from_the_file_is_kept_over_a_different_transcript() -> None:
    transcriber = _Transcriber("כתובת: ויצמן 5 חיפה")
    assert _stored("כתובת: הרצל 10 תל אביב", [_IMAGE], transcriber) == "כתובת: הרצל 10 תל אביב"
    assert transcriber.calls == 0


def test_a_page_image_without_text_is_stored_as_its_transcript() -> None:
    transcriber = _Transcriber("חשבון ארנונה\nכתובת: הרצל 10 תל אביב\n")
    assert _stored("", [_IMAGE], transcriber) == "חשבון ארנונה\nכתובת: הרצל 10 תל אביב"
    assert transcriber.calls == 1


def test_no_image_or_an_empty_transcript_leaves_the_text_empty() -> None:
    without_image = _Transcriber("כתובת: הרצל 10 תל אביב")
    assert _stored("", [], without_image) == ""
    assert without_image.calls == 0
    assert _stored("  \n", [_IMAGE], _Transcriber("  \n ")) == ""
    assert _stored("", [_IMAGE], None) == ""


def test_transcribe_without_a_key_returns_nothing_and_calls_no_model() -> None:
    client = GoogleGeminiClient(SimpleNamespace(gemini_api_key="", gemini_model="unused"))
    client._transcribe_sync = lambda images: pytest.fail("the model was called")  # type: ignore[method-assign]
    assert asyncio.run(client.transcribe([_IMAGE])) == ""


def test_a_failed_transcription_returns_nothing() -> None:
    client = GoogleGeminiClient(SimpleNamespace(gemini_api_key="test-key", gemini_model="unused"))

    def _fail(images: list[PageImage]) -> str:
        raise RuntimeError("offline")

    client._transcribe_sync = _fail  # type: ignore[method-assign]
    assert asyncio.run(client.transcribe([_IMAGE])) == ""
