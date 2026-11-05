import logging
from dataclasses import dataclass
from uuid import UUID

from app.core.config import Settings
from app.services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

_COLLECTION = "docket_labels"


@dataclass(frozen=True)
class LabeledExample:
    document_type: str
    excerpt: str
    score: float


class QdrantLearningStore:
    """Few-shot memory of human labels. Failures never block the case flow."""

    def __init__(self, settings: Settings, gemini: GeminiClient) -> None:
        self._settings = settings
        self._gemini = gemini
        self._client = None
        self._disabled = False

    def _enabled(self) -> bool:
        return bool(self._settings.qdrant_url and self._settings.gemini_api_key) and not self._disabled

    async def similar_examples(self, text: str, limit: int = 3) -> list[LabeledExample]:
        if not self._enabled() or not text.strip():
            return []
        try:
            vector = await self._gemini.embed(text[:4_000])
            import asyncio

            return await asyncio.to_thread(self._search, vector, limit)
        except Exception:
            logger.warning("Similar-example lookup skipped", exc_info=True)
            self._disabled = True
            return []

    async def record(
        self,
        *,
        document_id: UUID,
        document_type: str,
        process_type: str,
        anchors: list[str],
        structural_signature: str,
    ) -> str | None:
        if not self._enabled():
            return None
        from app.services.structural_excerpt import embedding_text

        excerpt = embedding_text(anchors)
        if not excerpt or not structural_signature:
            return None
        payload = {
            "document_id": str(document_id),
            "category_id": document_type,
            "document_type": document_type,
            "process_type": process_type,
            "structural_signature": structural_signature,
            "anchor_count": len(anchors),
            "excerpt": excerpt,
        }
        try:
            vector = await self._gemini.embed(excerpt)
            import asyncio

            await asyncio.to_thread(self._upsert, str(document_id), vector, payload)
            return str(document_id)
        except Exception:
            logger.warning("Could not store a human label embedding", exc_info=True)
            self._disabled = True
            return None

    def _qdrant(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            self._client = QdrantClient(url=self._settings.qdrant_url, timeout=1)
        return self._client

    def _ensure_collection(self, size: int) -> None:
        from qdrant_client.http.models import Distance, VectorParams

        client = self._qdrant()
        if client.collection_exists(_COLLECTION):
            return
        client.create_collection(
            collection_name=_COLLECTION,
            vectors_config=VectorParams(size=size, distance=Distance.COSINE),
        )

    def _search(self, vector: list[float], limit: int) -> list[LabeledExample]:
        self._ensure_collection(len(vector))
        response = self._qdrant().query_points(
            collection_name=_COLLECTION,
            query=vector,
            limit=limit,
            score_threshold=0.72,
        )
        examples: list[LabeledExample] = []
        for point in response.points:
            payload = point.payload or {}
            doc_type = str(payload.get("document_type") or payload.get("category_id") or "")
            excerpt = str(payload.get("excerpt") or "")
            if doc_type and excerpt:
                examples.append(LabeledExample(doc_type, excerpt, float(point.score or 0)))
        return examples

    def _upsert(self, point_id: str, vector: list[float], payload: dict) -> None:
        from qdrant_client.http.models import PointStruct

        self._ensure_collection(len(vector))
        self._qdrant().upsert(
            collection_name=_COLLECTION,
            points=[PointStruct(id=point_id, vector=vector, payload=payload)],
        )
