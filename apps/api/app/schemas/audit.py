from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    event_id: UUID
    case_id: UUID
    client_name: str | None
    case_name: str
    process_type: str
    action: str
    actor: str
    created_at: datetime
    # Identifiers, counts and hashes only, as on a case timeline. Never a typed value.
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditCenter(BaseModel):
    """The office's audit trail across all its cases, newest first."""

    # Counted over the whole office, whatever the filter.
    total_events: int
    signed_count: int
    smart_uploads_count: int
    vault_reuses_count: int
    revocations_count: int
    # How many events of each action the office has, for the filter.
    action_counts: dict[str, int] = Field(default_factory=dict)
    # How many events the filter matches; `events` holds the newest of them, up to the limit.
    matched_events: int
    events: list[AuditEvent]
