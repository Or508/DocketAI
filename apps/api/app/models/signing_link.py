import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base
from app.models.columns import new_uuid


class SigningLink(Base):
    __tablename__ = "signing_links"
    __table_args__ = (
        Index(
            "uq_signing_links_one_open",
            "case_id",
            unique=True,
            sqlite_where=text("revoked_at IS NULL AND completed_at IS NULL"),
            postgresql_where=text("revoked_at IS NULL AND completed_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoke_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    download_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    signed_file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chat_turns: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
