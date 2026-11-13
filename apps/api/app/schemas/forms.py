from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.gap import MissingRequirement, OpenSlot
from app.schemas.process import ValueSource

FillStatus = Literal[
    "ok",
    "overflow",
    "mismatch",
    "skipped_prefilled",
    "comb_unsupported",
    "awaiting_value",
]
DocumentRoleName = Literal["evidence", "form"]


class DocumentRoleUpdate(BaseModel):
    role: DocumentRoleName
    display_title: str | None = Field(default=None, max_length=120)

    @field_validator("display_title")
    @classmethod
    def _clean_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.split())
        if not cleaned or len(cleaned) > 120:
            raise ValueError("The display title must be 1 to 120 characters.")
        return cleaned


class DocumentRoleRead(BaseModel):
    document_id: UUID
    role: DocumentRoleName
    display_title: str | None = None


class FillReportField(BaseModel):
    field_name: str
    page: int
    slot_key: str
    status: FillStatus
    source: ValueSource | None = None


class FillReport(BaseModel):
    document_id: UUID
    fields: list[FillReportField]


class IntakeForm(BaseModel):
    document_id: UUID
    filename: str
    role: DocumentRoleName
    display_title: str | None = None
    widgets_total: int
    bound: int
    bound_empty: int
    unbound: int


class IntakeSummary(BaseModel):
    forms: list[IntakeForm]
    missing_documents: list[MissingRequirement]
    open_slots: list[OpenSlot]
    prompt_he: str
    prompt_en: str


SkipReason = Literal[
    "no_text_layer",
    "label_not_found",
    "ambiguous_match",
    "validator_rejected",
    "id_mismatch",
    "already_filled",
]


class SlotHit(BaseModel):
    slot_key: str
    rule: Literal["labeled", "unique", "composite"]
    label: str | None = None


class SlotSkip(BaseModel):
    slot_key: str
    reason: SkipReason
    rule: Literal["labeled", "unique", "composite"]
    label: str | None = None


class SlotConflict(BaseModel):
    slot_key: str
    value: str


class DocumentReadingReport(BaseModel):
    document_id: UUID
    filename: str
    document_type: str | None = None
    enabled: bool
    accepted: list[SlotHit]
    skips: list[SlotSkip]
    conflicts: list[SlotConflict]
    blocked: Literal["id_mismatch"] | None = None
