from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Purpose = Literal["intake", "signing"]
Channel = Literal["email", "whatsapp"]


class OutreachSendRequest(BaseModel):
    """Send the client a fresh link: to hand in documents, or to review and sign."""

    purpose: Purpose
    channel: Channel
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=32)
    reminders: bool = True


class OutreachMessage(BaseModel):
    id: UUID
    purpose: Purpose
    kind: Literal["first", "reminder"]
    channel: Channel
    recipient: str
    status: Literal["sent", "failed", "handed_to_office"]
    error: str | None
    created_at: datetime


class OutreachSent(BaseModel):
    message: OutreachMessage
    # The link itself, for the office to copy if it wants to.
    url: str
    # For WhatsApp: open this on the office's device; WhatsApp opens with the message written.
    whatsapp_url: str | None
    next_reminder_at: datetime | None


class OutreachState(BaseModel):
    email: str | None
    phone: str | None
    phone_display: str | None
    purpose: Purpose | None
    channel: Channel | None
    reminders_enabled: bool
    reminders_sent: int
    next_reminder_at: datetime | None
    stopped_reason: str | None
    email_available: bool
    messages: list[OutreachMessage]


class RemindersUpdate(BaseModel):
    enabled: bool


class DueReminder(BaseModel):
    """A WhatsApp reminder the office still has to send by hand."""

    case_id: UUID
    case_name: str
    client_name: str | None
    purpose: Purpose
    phone_display: str
    due_at: datetime
