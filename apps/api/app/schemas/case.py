from datetime import datetime
from typing import Literal
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


class CaseCertificate(BaseModel):
    case_reference: str
    channel: Literal["portal", "office"]
    signer_ip: str | None
    signer_user_agent: str | None
    consent_text: str
    created_at: datetime
    data_completed_at: datetime | None
    link_issued_at: datetime | None
    signed_at: datetime
    total_pages: int


class CaseAudit(BaseModel):
    is_signed: bool
    signed_at: datetime | None
    signer_verification_id: str | None
    content_sha256: str | None
    file_sha256: str | None
    certificate: CaseCertificate | None = None


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
    audit: CaseAudit
