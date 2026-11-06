from pydantic import BaseModel

from app.domain.enums import CaseStatus
from app.schemas.gap import PipelineProgress


class CaseProgressEvent(PipelineProgress):
    status: CaseStatus


class StreamError(BaseModel):
    detail: str
