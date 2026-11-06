import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base
from app.domain.enums import CaseStatus
from app.models.columns import JsonDict, JsonList, new_uuid, sa_enum


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(160))
    client_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    process_definition_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("process_definitions.id"),
        index=True,
    )
    status: Mapped[CaseStatus] = mapped_column(
        sa_enum(CaseStatus), default=CaseStatus.DRAFT, nullable=False
    )
    field_values: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    chat_history: Mapped[JsonList] = mapped_column(JSON, default=list)
    output_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    signer_verification_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    case_reference: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    content_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    certificate_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pipeline_stage: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    pipeline_message: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    pipeline_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pipeline_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    process_definition: Mapped["ProcessDefinition"] = relationship(
        back_populates="cases",
        lazy="selectin",
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
