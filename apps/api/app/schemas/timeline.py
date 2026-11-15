from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    id: UUID
    action: str
    actor: str
    created_at: datetime
    document_id: UUID | None
    # Identifiers and hashes only: document_type, role, verification_id,
    # superseded_verification_id, sha256 and the like. Never a typed value.
    metadata: dict[str, Any] = Field(default_factory=dict)
