import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base
from app.models.columns import UtcDateTime, new_uuid


class CaseOutreach(Base):
    """How the office reaches the client of one case, and where the reminders stand.

    One row per case. It points at the link that was last sent and keeps that link's raw token
    sealed with the server key (kept outside the database), so a reminder can carry the same link.
    The link tables themselves still keep only a hash.
    """

    __tablename__ = "case_outreach"

    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
    )
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # "intake" (hand in documents) or "signing" (review and sign).
    purpose: Mapped[str | None] = mapped_column(String(16), nullable=True)
    link_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    token_sealed: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    first_sent_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_reminder_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True, index=True)
    # Why reminders stopped: done, link_replaced, link_closed, case_signed, turned_off, schedule_done.
    stopped_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow, onupdate=utcnow)


class OutboundMessage(Base):
    """One message to a client: sent by email, or handed to the office as a WhatsApp link to send."""

    __tablename__ = "outbound_messages"
    __table_args__ = (Index("ix_outbound_messages_case_created", "case_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("cases.id", ondelete="CASCADE"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(16))
    # "first" or "reminder".
    kind: Mapped[str] = mapped_column(String(16))
    channel: Mapped[str] = mapped_column(String(16))
    recipient: Mapped[str] = mapped_column(String(320))
    # "sent", "failed", or "handed_to_office" (a WhatsApp link the office opens and sends itself).
    status: Mapped[str] = mapped_column(String(24))
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    actor: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
