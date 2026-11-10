from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentTypeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=160)
    label_he: str | None = None
    description: str = Field(min_length=1, max_length=500)
    min_count: int = Field(default=1, ge=1, le=10)


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=160)
    label_he: str | None = None
    field_type: Literal["text", "email", "phone", "date", "id_number"]
    pdf_field_name: str = Field(min_length=1, max_length=64)
    required: bool = True
    rtl: bool = False


ValueSource = Literal["client", "document", "office"]


class FieldSource(BaseModel):
    source: ValueSource
    document_id: UUID | None = None


class ProcessRead(BaseModel):
    key: str
    name: str
    description: str
    required_documents: list[DocumentTypeSpec]
    optional_documents: list[DocumentTypeSpec]
    required_fields: list[FieldSpec]
