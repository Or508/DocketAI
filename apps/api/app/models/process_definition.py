import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import utcnow
from app.db.base import Base
from app.models.columns import JsonDict, JsonList, new_uuid


class ProcessDefinition(Base):
    __tablename__ = "process_definitions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=new_uuid)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str] = mapped_column(Text)
    required_documents: Mapped[JsonList] = mapped_column(JSON, default=list)
    optional_documents: Mapped[JsonList] = mapped_column(JSON, default=list)
    required_fields: Mapped[JsonList] = mapped_column(JSON, default=list)
    template_filename: Mapped[str] = mapped_column(String(255))
    layout: Mapped[JsonDict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    cases: Mapped[list["Case"]] = relationship(back_populates="process_definition", lazy="raise")
