from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.case import CaseRead
from app.schemas.chat import ChatMessageRead
from app.schemas.forms import DocumentReadingReport
from app.schemas.gap import GapReport, OpenSlot, UnboundAnchor
from app.schemas.process import FieldSource, FieldSpec, ProcessRead


class FileRejection(BaseModel):
    filename: str
    reason: str


class CaseWorkspace(BaseModel):
    case: CaseRead
    gap: GapReport
    process: ProcessRead
    messages: list[ChatMessageRead]
    field_values: dict[str, str]
    field_sources: dict[str, FieldSource] = Field(default_factory=dict)
    missing_fields: list[FieldSpec]
    open_slots: list[OpenSlot] = Field(default_factory=list)
    unbound_anchors: list[UnboundAnchor] = Field(default_factory=list)
    ready_to_sign: bool
    signing_blockers: list[str]
    consent_text: str
    readings: list[DocumentReadingReport] = Field(default_factory=list)


class UploadResult(BaseModel):
    workspace: CaseWorkspace
    job_id: str | None = None
    accepted_filenames: list[str] = Field(default_factory=list)
    skipped_duplicates: list[str] = Field(default_factory=list)
    rejected: list[FileRejection] = Field(default_factory=list)


class RoutedFile(BaseModel):
    """Where one dropped file went, and what decided it."""

    filename: str
    # routed: filed in a drawer or as the form. unrouted: kept on the case for the office to file.
    outcome: Literal["routed", "unrouted", "rejected"]
    role: str | None = None
    document_type: str | None = None
    drawer_label_he: str | None = None
    matched_by: Literal["form", "filename", "content", "filename_and_content"] | None = None
    document_id: UUID | None = None
    status: str | None = None
    # The case already held this exact file; it was filed, not stored again.
    duplicate: bool = False
    reason: str | None = None


class SmartUploadResult(CaseWorkspace):
    """The workspace after a smart upload, with one line per dropped file."""

    routed_files: list[RoutedFile] = Field(default_factory=list)
