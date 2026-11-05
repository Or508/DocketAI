from uuid import uuid4

from app.domain.classification import DocumentClassification, normalize_classification
from app.domain.enums import CaseStatus, ClassificationSource, DocumentStatus
from app.domain.documents import DocumentView
from app.domain.readiness import signing_blockers
from app.schemas.process import DocumentTypeSpec
from app.services.gap_analyzer import GapAnalyzer


def _doc(
    doc_type: str | None,
    status: DocumentStatus,
    source: ClassificationSource = ClassificationSource.AUTO,
    confidence: float | None = 0.9,
) -> DocumentView:
    return DocumentView(
        document_id=uuid4(),
        filename=f"{doc_type or 'file'}.pdf",
        document_type=doc_type,
        confidence=confidence,
        status=status,
        source=source,
        rationale=None,
        error_message=None,
    )


def test_missing_and_unrecognized_are_separate() -> None:
    requirement = DocumentTypeSpec(
        type_key="id_copy",
        label="Government ID",
        description="Identity document.",
        min_count=1,
    )
    low = _doc("id_copy", DocumentStatus.NEEDS_REVIEW, confidence=0.4)
    report = GapAnalyzer(0.75).analyze(
        case_id=uuid4(),
        status=CaseStatus.READY_FOR_REVIEW,
        requirements=[requirement],
        labels={"id_copy": "Government ID"},
        label_he={"id_copy": "צילום תעודת זהות"},
        documents=[low],
    )
    assert report.total_files == 1
    assert report.identified == []
    assert report.missing[0].found_count == 0
    assert report.unrecognized[0].suggested_type == "id_copy"


def test_human_label_satisfies_requirement() -> None:
    requirement = DocumentTypeSpec(
        type_key="id_copy",
        label="Government ID",
        description="Identity document.",
    )
    confirmed = _doc("id_copy", DocumentStatus.CLASSIFIED, ClassificationSource.HUMAN, 1.0)
    report = GapAnalyzer(0.75).analyze(
        case_id=uuid4(),
        status=CaseStatus.FILLING,
        requirements=[requirement],
        labels={"id_copy": "Government ID"},
        label_he={"id_copy": None},
        documents=[confirmed],
    )
    assert report.missing == []
    assert report.identified[0].source == ClassificationSource.HUMAN


def test_low_confidence_classified_does_not_count() -> None:
    requirement = DocumentTypeSpec(
        type_key="tax_form",
        label="Tax form",
        description="Tax form.",
        min_count=2,
    )
    strong = _doc("tax_form", DocumentStatus.CLASSIFIED, confidence=0.91)
    weak = _doc("tax_form", DocumentStatus.CLASSIFIED, confidence=0.5)
    report = GapAnalyzer(0.75).analyze(
        case_id=uuid4(),
        status=CaseStatus.READY_FOR_REVIEW,
        requirements=[requirement],
        labels={"tax_form": "Tax form"},
        label_he={},
        documents=[strong, weak],
    )
    assert report.missing[0].found_count == 1
    assert report.missing[0].required_count == 2
    assert len(report.unrecognized) == 1


def test_normalize_rejects_types_outside_the_catalog() -> None:
    raw = DocumentClassification(document_type="passport_scan", confidence=0.99, needs_human_review=False)
    normalized = normalize_classification(raw, {"id_copy"}, 0.75)
    assert normalized.document_type == "unknown"
    assert normalized.needs_human_review is True


def test_signing_blockers_clear_only_when_the_file_is_complete() -> None:
    blocked = signing_blockers(
        status=CaseStatus.READY_FOR_REVIEW,
        missing_labels=["Government ID"],
        unrecognized_count=1,
        in_progress_count=0,
        missing_field_labels=["Email"],
    )
    assert any("review" in reason for reason in blocked)
    assert any("Government ID" in reason for reason in blocked)
    ready = signing_blockers(
        status=CaseStatus.FILLING,
        missing_labels=[],
        unrecognized_count=0,
        in_progress_count=0,
        missing_field_labels=[],
    )
    assert ready == []
