from pydantic import BaseModel, Field

from app.schemas.case import CaseRead
from app.schemas.chat import ChatMessageRead
from app.schemas.gap import GapReport
from app.schemas.process import FieldSpec, ProcessRead


class FileRejection(BaseModel):
    filename: str
    reason: str


class CaseWorkspace(BaseModel):
    case: CaseRead
    gap: GapReport
    process: ProcessRead
    messages: list[ChatMessageRead]
    field_values: dict[str, str]
    missing_fields: list[FieldSpec]
    ready_to_sign: bool
    signing_blockers: list[str]


class UploadResult(BaseModel):
    workspace: CaseWorkspace
    job_id: str | None = None
    accepted_filenames: list[str] = Field(default_factory=list)
    skipped_duplicates: list[str] = Field(default_factory=list)
    rejected: list[FileRejection] = Field(default_factory=list)
