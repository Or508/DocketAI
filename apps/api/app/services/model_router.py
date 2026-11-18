"""One model client in front of two providers: the main one, and a backup when it is down.

The office's chosen provider (AI_PROVIDER, Claude by default) answers first. If it has no key,
or a call fails, the same call goes to the other provider. Embeddings always come from the
provider that has them (Gemini), because the stored vectors must all come from one model.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from app.domain.ai_policy import ai_allowed
from app.domain.classification import DocumentClassification, FieldExtraction
from app.schemas.process import FieldSpec
from app.services.document_processor import PageImage
from app.services.gemini_client import GeminiClient, GeminiUnavailable

logger = logging.getLogger(__name__)


class RoutedModelClient:
    def __init__(self, primary: GeminiClient, backup: GeminiClient, embedder: GeminiClient) -> None:
        self.primary = primary
        self.backup = backup
        self._embedder = embedder

    @property
    def configured(self) -> bool:
        return ai_allowed() and (self.primary.configured or self.backup.configured)

    def _order(self) -> list[GeminiClient]:
        if not ai_allowed():
            return []
        return [client for client in (self.primary, self.backup) if client.configured]

    async def _first(self, call: str, **kwargs):
        clients = self._order()
        if not clients:
            raise GeminiUnavailable("AI is off for this office" if not ai_allowed() else "No AI provider is configured")
        last: Exception | None = None
        for client in clients:
            try:
                return await getattr(client, call)(**kwargs)
            except Exception as exc:  # the next provider gets the same call
                last = exc
                logger.warning("%s failed on %s; trying the backup", call, type(client).__name__)
        assert last is not None
        raise last

    async def classify_document(
        self,
        *,
        system: str,
        prompt: str,
        images: list[PageImage],
    ) -> DocumentClassification:
        return await self._first("classify_document", system=system, prompt=prompt, images=images)

    async def extract_fields(self, *, message: str, fields: list[FieldSpec]) -> FieldExtraction:
        return await self._first("extract_fields", message=message, fields=fields)

    async def transcribe(self, images: list[PageImage]) -> str:
        # Each client returns "" rather than raising, so an empty page goes on to the backup.
        for client in self._order():
            text = await client.transcribe(images)
            if text:
                return text
        return ""

    async def stream_text(self, *, system: str, prompt: str) -> AsyncIterator[str]:
        clients = self._order()
        if not clients:
            raise GeminiUnavailable("No AI provider is configured")
        for index, client in enumerate(clients):
            started = False
            try:
                async for chunk in client.stream_text(system=system, prompt=prompt):
                    started = True
                    yield chunk
                return
            except Exception:
                # Once words reached the reader, switching models mid-answer would garble it.
                if started or index == len(clients) - 1:
                    raise
                logger.warning("Streaming failed on %s; trying the backup", type(client).__name__)

    async def embed(self, text: str) -> list[float]:
        if not ai_allowed():
            raise GeminiUnavailable("AI is off for this office")
        return await self._embedder.embed(text)
