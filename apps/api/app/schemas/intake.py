from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class IntakeLinkCreated(BaseModel):
    """Shown to the office once. The token is not stored and cannot be read again."""

    case_id: UUID
    token: str
    url_path: str
    expires_at: datetime | None


class IntakeDrawer(BaseModel):
    document_type: str
    label_he: str
    filled: bool
    filename: str | None = None


class IntakeStatus(BaseModel):
    """What the client's page may know: which documents are needed and which arrived.

    No value read from a document or typed by the office is ever part of this.
    """

    case_id: UUID
    client_name: str
    process_type: str
    process_title_he: str
    status: str
    required_drawers: list[IntakeDrawer]
    all_drawers_filled: bool


class IntakeRoutedFile(BaseModel):
    filename: str
    # received: filed in a drawer. pending: kept for the office to file. rejected: not stored.
    outcome: Literal["received", "pending", "rejected"]
    document_type: str | None = None
    label_he: str | None = None
    reason_he: str | None = None


class IntakeUploadResult(IntakeStatus):
    routed_files: list[IntakeRoutedFile] = Field(default_factory=list)
