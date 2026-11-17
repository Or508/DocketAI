from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class IntegrityCheck(BaseModel):
    code: str
    label_he: str
    status: Literal["pass", "warn", "fail"]
    detail_he: str
    # The slot or drawer the check points at, when it points at one.
    field_key: str | None = None
    drawer_type: str | None = None


class IntegrityReport(BaseModel):
    case_id: UUID
    # block: at least one check failed. warn: none failed, at least one needs a look.
    status: Literal["pass", "warn", "block"]
    score: int
    checks: list[IntegrityCheck]
