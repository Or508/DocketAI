import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.domain.enums import AuditAction, ClassificationSource, DocumentStatus
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.domain.form_anchors import bind_widget
from app.schemas.process import DocumentTypeSpec, FieldSpec
from app.services.classification_engine import ClassificationEngine
from app.services.document_processor import DocumentProcessor
from app.services.learning_store import QdrantLearningStore
from app.services.object_store import ObjectStore
from app.services.pdf_filler import read_form_widgets
from app.services.structural_excerpt import anchors_from_text, embedding_text

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        processor: DocumentProcessor,
        classifier: ClassificationEngine,
        learning: QdrantLearningStore,
        store: ObjectStore,
    ) -> None:
        self._processor = processor
        self._classifier = classifier
        self._learning = learning
        self._store = store

    async def process_document(
        self,
        session: AsyncSession,
        document: Document,
        types: list[DocumentTypeSpec],
        organization_id: UUID,
        fields: list[FieldSpec] | None = None,
    ) -> None:
        async with self._store.local_copy(document.storage_path) as path:
            extraction = await self._processor.extract(path)
            if fields is not None and document.mime_type == "application/pdf":
                document.form_anchors = await _form_anchors(path, fields, document.id)
        document.page_count = extraction.page_count
        document.extracted_text = extraction.text or None
        document.error_message = None
        document.updated_at = utcnow()
        anchors = anchors_from_text(extraction.text)
        examples = await self._learning.similar_examples(embedding_text(anchors), organization_id)
        result = await self._classifier.classify(
            filename=document.original_filename,
            extraction=extraction,
            types=types,
            examples=examples,
        )
        document.document_type = result.document_type
        document.confidence = result.confidence
        document.language = (result.language or "")[:16] or None
        document.summary = (result.summary or "")[:500] or None
        document.rationale = result.rationale or None
        document.classification_source = ClassificationSource.AUTO
        document.status = (
            DocumentStatus.NEEDS_REVIEW if result.needs_human_review else DocumentStatus.CLASSIFIED
        )
        session.add(
            AuditLog(
                case_id=document.case_id,
                document_id=document.id,
                action=AuditAction.AUTO_CLASSIFY,
                actor="system",
                new_value={
                    "document_type": result.document_type,
                    "confidence": result.confidence,
                    "needs_human_review": result.needs_human_review,
                },
            )
        )
        logger.info(
            "Classified %s as %s (%.2f, review=%s)",
            document.id,
            result.document_type,
            result.confidence,
            result.needs_human_review,
        )


async def _form_anchors(path, fields: list[FieldSpec], document_id: UUID) -> list[dict] | None:
    """Record each text widget and the slot it binds to. A read failure leaves no anchors."""
    try:
        readings = await asyncio.to_thread(read_form_widgets, path)
    except Exception:
        logger.warning("Could not read form widgets on document %s", document_id)
        return None
    anchors: list[dict] = []
    for reading in readings:
        binding = bind_widget(reading.field_name, fields)
        anchors.append(
            {
                "field_name": reading.field_name,
                "page": reading.page_index,
                "rect": list(reading.rect),
                "empty": reading.empty,
                "value": None if reading.empty else reading.value,
                "slot_key": binding.key if binding else None,
                "match": binding.match if binding else None,
            }
        )
    return anchors
