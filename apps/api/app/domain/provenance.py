"""Deterministic reasons a slot is asked. Built from stored data, never from a model."""

from __future__ import annotations

from app.models.case import Case
from app.models.document import Document
from app.schemas.gap import WhyItem
from app.schemas.process import FieldSpec, Provenance

OFFICE_FORM_TITLE_HE = "טופס המשרד"
OFFICE_FORM_TITLE_EN = "the office form"

INTAKE_PROMPT_HE = "הנה מה שזיהינו שחסר בתיק – האם להוסיף מסמכים או פרטים נוספים שהבוט יבקש מהלקוח?"
INTAKE_PROMPT_EN = (
    "Here is what we found missing in the case – should we add documents or further details "
    "for the bot to ask the client?"
)


def why_items(case: Case, spec: FieldSpec) -> list[WhyItem]:
    """Template reason first, then one item per office form that still has an empty bound widget."""
    items: list[WhyItem] = []
    template = _template_item(spec.provenance)
    if template is not None:
        items.append(template)
    documents = sorted(
        (document for document in case.documents if document.role == "form"),
        key=lambda document: (document.created_at, str(document.id)),
    )
    for document in documents:
        page = _empty_bound_page(document, spec.key)
        if page is None:
            continue
        title = (document.display_title or "").strip()
        title_he = title or OFFICE_FORM_TITLE_HE
        title_en = title or OFFICE_FORM_TITLE_EN
        items.append(
            WhyItem(
                kind="form",
                text_he=f"הפרט נדרש כדי למלא עבורך שדה ב«{title_he}» (עמוד {page + 1}).",
                text_en=(
                    f"This detail is required to fill a field for you in «{title_en}» (page {page + 1})."
                ),
                document_id=document.id,
                page=page,
            )
        )
    return items


def public_why(items: list[WhyItem]) -> list[WhyItem]:
    """Portal copy: the sentences stay, and the office identifiers are removed."""
    return [item.model_copy(update={"document_id": None, "page": None}) for item in items]


def _template_item(provenance: Provenance | None) -> WhyItem | None:
    if provenance is None:
        return None
    parts = (
        provenance.form_he,
        provenance.section_he,
        provenance.purpose_he,
        provenance.form_en,
        provenance.section_en,
        provenance.purpose_en,
    )
    if not any(part and part.strip() for part in parts):
        return None
    section_he = provenance.section_he or ""
    form_he = provenance.form_he or ""
    purpose_he = provenance.purpose_he or ""
    section_en = provenance.section_en or ""
    form_en = provenance.form_en or ""
    purpose_en = provenance.purpose_en or ""
    return WhyItem(
        kind="template",
        text_he=f"הפרט נדרש כדי למלא את {section_he} ב{form_he}. {purpose_he}",
        text_en=f"This detail is required to fill the {section_en} in the {form_en}. {purpose_en}",
        document_id=None,
        page=None,
    )


def _empty_bound_page(document: Document, slot_key: str) -> int | None:
    for anchor in document.form_anchors or []:
        if not isinstance(anchor, dict):
            continue
        if anchor.get("slot_key") != slot_key or not anchor.get("empty"):
            continue
        try:
            return int(anchor.get("page", 0))
        except (TypeError, ValueError):
            return 0
    return None
