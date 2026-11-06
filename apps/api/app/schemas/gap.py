from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import CaseStatus, ClassificationSource, DocumentStatus

PipelineStage = Literal[
    "draft",
    "parsing",
    "classifying",
    "auditing",
    "awaiting_input",
    "ready_for_signature",
    "signed",
    "failed",
]


class PipelineProgress(BaseModel):
    stage: PipelineStage = "draft"
    completed: int = 0
    total: int = 0
    message: str = ""


class IdentifiedDocument(BaseModel):
    document_id: UUID
    filename: str
    document_type: str
    label: str
    label_he: str | None = None
    confidence: float | None
    source: ClassificationSource


class MissingRequirement(BaseModel):
    type_key: str
    label: str
    label_he: str | None = None
    required_count: int
    found_count: int


class UnrecognizedDocument(BaseModel):
    document_id: UUID
    filename: str
    suggested_type: str | None
    confidence: float | None
    rationale: str | None


class InProgressDocument(BaseModel):
    document_id: UUID
    filename: str
    status: DocumentStatus


class GapReport(BaseModel):
    case_id: UUID
    status: CaseStatus
    total_files: int
    identified: list[IdentifiedDocument]
    missing: list[MissingRequirement]
    unrecognized: list[UnrecognizedDocument]
    in_progress: list[InProgressDocument]
    pipeline: PipelineProgress = Field(default_factory=PipelineProgress)


class ManualClassifyRequest(BaseModel):
    document_id: UUID
    document_type: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


class FillAndSignRequest(BaseModel):
    field_values: dict[str, str] = Field(default_factory=dict)
    signature_png_base64: str = Field(min_length=20, max_length=3_000_000)
    consent: Literal[True]
