from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

NOTE_MAX_LENGTH = 2000


class NoteCreate(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def _body(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("A note cannot be empty.")
        if len(cleaned) > NOTE_MAX_LENGTH:
            raise ValueError(f"A note can hold up to {NOTE_MAX_LENGTH} characters.")
        return cleaned


class NoteRead(BaseModel):
    id: UUID
    case_id: UUID
    author_email: str
    body: str
    created_at: datetime
