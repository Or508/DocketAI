from pydantic import BaseModel, Field


class DocumentClassification(BaseModel):
    document_type: str
    confidence: float = Field(ge=0, le=1)
    language: str = ""
    summary: str = ""
    rationale: str = ""
    needs_human_review: bool = False


class FieldHit(BaseModel):
    key: str
    value: str


class FieldExtraction(BaseModel):
    fields: list[FieldHit] = Field(default_factory=list)


def normalize_classification(
    raw: DocumentClassification,
    allowed: set[str],
    threshold: float,
) -> DocumentClassification:
    document_type = raw.document_type.strip()
    confidence = min(1.0, max(0.0, float(raw.confidence)))
    needs_review = raw.needs_human_review
    if document_type not in allowed:
        document_type = "unknown"
        needs_review = True
    if document_type == "unknown" or confidence < threshold:
        needs_review = True
    return raw.model_copy(
        update={
            "document_type": document_type,
            "confidence": confidence,
            "needs_human_review": needs_review,
        }
    )
