from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import CaseStatus


class CaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    process_key: str = Field(min_length=1, max_length=64)
    client_name: str | None = Field(default=None, max_length=160)

    def normalized(self) -> "CaseCreate":
        client = self.client_name.strip() if self.client_name else None
        return self.model_copy(
            update={
                "name": self.name.strip(),
                "process_key": self.process_key.strip(),
                "client_name": client or None,
            }
        )


class CaseRead(BaseModel):
    id: UUID
    name: str
    client_name: str | None
    status: CaseStatus
    process_key: str
    process_name: str
    document_count: int
    download_ready: bool
    created_at: datetime
    updated_at: datetime
