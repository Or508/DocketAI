from uuid import UUID

from app.domain.documents import DocumentView
from app.domain.enums import CaseStatus, ClassificationSource, DocumentStatus
from app.schemas.gap import (
    GapReport,
    IdentifiedDocument,
    InProgressDocument,
    MissingRequirement,
    UnrecognizedDocument,
)
from app.schemas.process import DocumentTypeSpec


class GapAnalyzer:
    """Compare accepted classifications with a process's required document types.

    A suggestion on an unrecognized file does not satisfy a requirement.
    Only human-confirmed files, or automatic classifications at or above the
    confidence threshold, count as identified.
    """

    def __init__(self, confidence_threshold: float) -> None:
        self._threshold = confidence_threshold

    def analyze(
        self,
        *,
        case_id: UUID,
        status: CaseStatus,
        requirements: list[DocumentTypeSpec],
        labels: dict[str, str],
        label_he: dict[str, str | None],
        documents: list[DocumentView],
    ) -> GapReport:
        identified: list[IdentifiedDocument] = []
        unrecognized: list[UnrecognizedDocument] = []
        in_progress: list[InProgressDocument] = []
        counts: dict[str, int] = {item.type_key: 0 for item in requirements}

        for document in documents:
            if document.status in {DocumentStatus.UPLOADED, DocumentStatus.PROCESSING}:
                in_progress.append(
                    InProgressDocument(
                        document_id=document.document_id,
                        filename=document.filename,
                        status=document.status,
                    )
                )
                continue
            if self._accepted(document):
                doc_type = document.document_type or "unknown"
                identified.append(
                    IdentifiedDocument(
                        document_id=document.document_id,
                        filename=document.filename,
                        document_type=doc_type,
                        label=labels.get(doc_type, doc_type),
                        label_he=label_he.get(doc_type),
                        confidence=document.confidence,
                        source=document.source,
                    )
                )
                if doc_type in counts:
                    counts[doc_type] += 1
                continue
            suggested = document.document_type if document.document_type not in {None, "", "unknown"} else None
            unrecognized.append(
                UnrecognizedDocument(
                    document_id=document.document_id,
                    filename=document.filename,
                    suggested_type=suggested,
                    confidence=document.confidence,
                    rationale=document.error_message or document.rationale or "Needs a human classification.",
                )
            )

        missing = [
            MissingRequirement(
                type_key=item.type_key,
                label=item.label,
                label_he=item.label_he,
                required_count=item.min_count,
                found_count=counts[item.type_key],
            )
            for item in requirements
            if counts[item.type_key] < item.min_count
        ]
        identified.sort(key=lambda item: item.filename.lower())
        unrecognized.sort(key=lambda item: item.filename.lower())
        return GapReport(
            case_id=case_id,
            status=status,
            total_files=len(documents),
            identified=identified,
            missing=missing,
            unrecognized=unrecognized,
            in_progress=in_progress,
        )

    def _accepted(self, document: DocumentView) -> bool:
        if document.status != DocumentStatus.CLASSIFIED:
            return False
        if not document.document_type or document.document_type == "unknown":
            return False
        if document.source == ClassificationSource.HUMAN:
            return True
        return document.confidence is not None and document.confidence >= self._threshold
