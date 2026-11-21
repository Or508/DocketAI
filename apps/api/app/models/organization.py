import uuid
from datetime import datetime

from sqlalchemy import Boolean, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base
from app.models.columns import UtcDateTime, new_uuid


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(160))
    # What kind of office this is (app/domain/professions.py): which processes it sees and its words.
    profession: Mapped[str] = mapped_column(String(40), default="law", server_default="law", nullable=False)
    # Off: no document, page, or chat message of this office is sent to an AI model (ai_policy.py).
    ai_reading_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    # How a client reaches the office. Shown on the client's signing and upload pages.
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    # Set only for a public demo office. Real offices stay null, and cleanup deletes a demo once this moment has passed.
    demo_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime(), default=utcnow)
