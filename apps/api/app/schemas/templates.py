from typing import Literal

from pydantic import BaseModel


class TemplateDrawer(BaseModel):
    id: str
    label_he: str
    accepted_document_types: list[str]
    required: bool
    # The slots a file in this drawer can supply, in form order.
    reads_fields: list[str]


class TemplateFieldSource(BaseModel):
    drawer_id: str
    label_he: str


class TemplateFieldTarget(BaseModel):
    # 1-based page of the blank form, when the blank is on this server to be read.
    page: int | None
    mode: Literal["digit_boxes", "text"] | None
    section_he: str | None


class TemplateField(BaseModel):
    key: str
    label_he: str
    field_type: str
    required: bool
    # Drawers that can fill this slot, first choice first. Empty: typed by a person.
    sources: list[TemplateFieldSource]
    target: TemplateFieldTarget


class TemplateCaseCounts(BaseModel):
    total: int
    # Every case of this office that is not signed yet.
    filling: int
    signed: int


class TemplateRead(BaseModel):
    process_type: str
    title_he: str
    description_he: str
    form_source: Literal["official_blank", "generated"]
    default_template_available: bool
    required_drawers: list[TemplateDrawer]
    mapped_fields: list[TemplateField]
    case_counts: TemplateCaseCounts
