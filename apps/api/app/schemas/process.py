from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReadingPart(BaseModel):
    """One piece of a composite slot, matched by a closed label list."""

    model_config = ConfigDict(extra="forbid")

    labels: list[str] = Field(min_length=1)


class ReadingRule(BaseModel):
    """One closed way a document type may supply a slot."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["labeled", "unique", "composite"]
    slot_key: str = Field(min_length=1, max_length=64)
    labels: list[str] = Field(default_factory=list)
    parts: list[ReadingPart] = Field(default_factory=list)
    # The labeled value is one printed address line; this rule takes one piece of it.
    piece: Literal["street", "house_number", "city"] | None = None


class DocumentReading(BaseModel):
    """Reading stays off until a real sample set produced no wrong values."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    one_person: bool = False
    rules: list[ReadingRule] = Field(default_factory=list)


class DocumentTypeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=160)
    label_he: str | None = None
    description: str = Field(min_length=1, max_length=500)
    min_count: int = Field(default=1, ge=1, le=10)
    reading: DocumentReading | None = None


class Provenance(BaseModel):
    """Where a template slot is written, in neutral language. No legal conclusion."""

    model_config = ConfigDict(extra="forbid")

    form_he: str | None = Field(default=None, max_length=200)
    section_he: str | None = Field(default=None, max_length=200)
    purpose_he: str | None = Field(default=None, max_length=200)
    form_en: str | None = Field(default=None, max_length=200)
    section_en: str | None = Field(default=None, max_length=200)
    purpose_en: str | None = Field(default=None, max_length=200)


class FieldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=160)
    label_he: str | None = None
    field_type: Literal["text", "email", "phone", "date", "id_number"]
    pdf_field_name: str = Field(min_length=1, max_length=64)
    required: bool = True
    rtl: bool = False
    provenance: Provenance | None = None


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
