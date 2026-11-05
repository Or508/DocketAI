from dataclasses import dataclass
from uuid import UUID

from app.domain.enums import ClassificationSource, DocumentStatus


@dataclass(frozen=True)
class DocumentView:
    document_id: UUID
    filename: str
    document_type: str | None
    confidence: float | None
    status: DocumentStatus
    source: ClassificationSource
    rationale: str | None
    error_message: str | None
