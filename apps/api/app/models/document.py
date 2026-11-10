import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base
from app.domain.enums import ClassificationSource, DocumentStatus
from app.models.columns import JsonList, new_uuid, sa_enum


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("case_id", "content_hash", name="uq_document_case_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)
    case_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("cases.id", ondelete="CASCADE"),
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(1024))
    mime_type: Mapped[str] = mapped_column(String(128))
    file_size: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(
        sa_enum(DocumentStatus), default=DocumentStatus.UPLOADED, nullable=False
    )
    classification_source: Mapped[ClassificationSource] = mapped_column(
        sa_enum(ClassificationSource),
        default=ClassificationSource.PENDING,
        nullable=False,
    )
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Text widgets of an uploaded AcroForm: name, page, rect, emptiness and the bound slot.
    form_anchors: Mapped[JsonList | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    case: Mapped["Case"] = relationship(back_populates="documents", lazy="raise")
