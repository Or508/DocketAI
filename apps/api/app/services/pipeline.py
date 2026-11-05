import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.domain.enums import AuditAction, ClassificationSource, DocumentStatus
from app.models.audit_log import AuditLog
from app.models.document import Document
from app.schemas.process import DocumentTypeSpec
from app.services.classification_engine import ClassificationEngine
from app.services.document_processor import DocumentProcessor
from app.services.learning_store import QdrantLearningStore
from app.services.structural_excerpt import anchors_from_text, embedding_text

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(
        self,
        processor: DocumentProcessor,
        classifier: ClassificationEngine,
        learning: QdrantLearningStore,
    ) -> None:
        self._processor = processor
        self._classifier = classifier
        self._learning = learning

    async def process_document(
        self,
        session: AsyncSession,
        document: Document,
        types: list[DocumentTypeSpec],
    ) -> None:
        extraction = await self._processor.extract(Path(document.storage_path))
        document.page_count = extraction.page_count
        document.extracted_text = extraction.text or None
        document.error_message = None
        document.updated_at = utcnow()
        anchors = anchors_from_text(extraction.text)
        examples = await self._learning.similar_examples(embedding_text(anchors))
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
