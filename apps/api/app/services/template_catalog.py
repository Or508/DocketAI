"""The office's form catalog: what each process collects, reads and fills."""

import asyncio
import logging
import uuid
from functools import lru_cache
from pathlib import Path

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.case_scope import CaseScope, case_query
from app.domain.enums import CaseStatus
from app.models.case import Case
from app.models.process_definition import ProcessDefinition
from app.schemas.process import DocumentTypeSpec, FieldSpec
from app.services.default_forms import default_form
from app.schemas.templates import (
    TemplateCaseCounts,
    TemplateDrawer,
    TemplateField,
    TemplateFieldSource,
    TemplateFieldTarget,
    TemplateRead,
)

logger = logging.getLogger(__name__)

_documents = TypeAdapter(list[DocumentTypeSpec])
_fields = TypeAdapter(list[FieldSpec])

_ORDER = {"bl_6101": 0, "onboarding": 1, "real_estate": 2, "employee_onboarding": 3}
_TEXT_HE: dict[str, tuple[str, str]] = {
    "bl_6101": (
        "בל/6101 – דיווח רב-שנתי לביטוח לאומי",
        "טופס רשמי ריק שמתמלא מתוך מסמכי הלקוח. המשרד בודק את הפרטים האישיים, והלקוח חותם על הטופס עצמו.",
    ),
    "employee_onboarding": (
        "טופס 101 – כרטיס עובד ובקשה להקלה ולתיאום מס",
        "טופס 101 ריק שמתמלא מתוך מסמכי העובד: תעודת זהות, חשבון ארנונה ואישור בנק. המשרד בודק את הפרטים, והעובד חותם על הטופס עצמו.",
    ),
    "onboarding": (
        "טופס 101 – קליטת עובד חדש",
        "מסמכי זהות, מס ובנק של עובד חדש. הפרטים מתמלאים על טופס 101 ריק, והעובד חותם על הטופס עצמו.",
    ),
    "real_estate": (
        "עסקת מקרקעין",
        "תיק רכישה: הסכם מכר, נסח טאבו, זיהוי הצדדים ואישורי מס. הפרטים מתמלאים על טופס העסקה, והרוכש חותם על הטופס עצמו.",
    ),
}
# The everyday name of the document a drawer holds, as shown beside a field it fills.
_SOURCE_HE = {
    "id_copy": "תעודת זהות",
    "proof_of_address": "חשבון ארנונה",
    "bank_confirmation": "אישור בנק",
    "tax_form": "טופס 101",
    "title_deed": "נסח טאבו",
}


def default_template_path(process: ProcessDefinition, settings: Settings) -> Path:
    blank = default_form(process.key, settings)
    if blank is not None:
        return blank.path
    if (process.layout or {}).get("sign_source") == "uploaded_form":
        # A process that signs an uploaded form and offers no blank has nothing on disk.
        return settings.resolved_template_dir / "no-default-form"
    return settings.resolved_template_dir / process.template_filename


def _fills_blank(process: ProcessDefinition, settings: Settings) -> bool:
    """True when a new case of this process starts from a blank form put on the case."""
    return (process.layout or {}).get("sign_source") == "uploaded_form" or default_form(
        process.key, settings
    ) is not None


@lru_cache(maxsize=8)
def _blank_targets(path: str, stamp: tuple[int, int], process_key: str) -> dict[str, tuple[int, str]]:
    """Where each slot lands on the blank form: slot -> (1-based page, mode). Keyed by the file's stamp."""
    from app.catalog.processes import PROCESSES
    from app.services.flat_form import FlatProfile, read_flat_anchors

    seed = next((item for item in PROCESSES if item.key == process_key), None)
    if seed is None:
        return {}
    anchors = read_flat_anchors(
        Path(path), _fields.validate_python(seed.required_fields), FlatProfile.from_layout(seed.layout)
    )
    return {
        str(anchor["slot_key"]): (
            int(anchor["page"]) + 1,
            "digit_boxes" if anchor.get("target") == "comb" else "text",
        )
        for anchor in anchors
    }


async def _targets(
    process: ProcessDefinition, path: Path, available: bool, blank: bool
) -> dict[str, tuple[int, str]]:
    layout = process.layout or {}
    if not blank:
        page = int(layout.get("page_index", 0)) + 1
        return {str(item.get("key")): (page, "text") for item in process.required_fields or []}
    if not available:
        return {}
    try:
        stat = path.stat()
        return await asyncio.to_thread(_blank_targets, str(path), (stat.st_mtime_ns, stat.st_size), process.key)
    except Exception:
        logger.exception("Could not read the blank form of process %s", process.key)
        return {}


async def list_templates(
    session: AsyncSession, settings: Settings, scope: CaseScope
) -> list[TemplateRead]:
    processes = (await session.scalars(select(ProcessDefinition))).all()
    # Counted through the caller's own scope, so another office's cases never add up here.
    counted = (
        case_query(scope)
        .with_only_columns(Case.process_definition_id, Case.status, func.count())
        .group_by(Case.process_definition_id, Case.status)
    )
    totals: dict[uuid.UUID, list[int]] = {}
    for process_id, status, count in (await session.execute(counted)).all():
        entry = totals.setdefault(process_id, [0, 0])
        entry[0] += int(count)
        if status == CaseStatus.SIGNED:
            entry[1] += int(count)

    result: list[TemplateRead] = []
    for process in sorted(processes, key=lambda item: (_ORDER.get(item.key, len(_ORDER)), item.name)):
        layout = process.layout or {}
        required = _documents.validate_python(process.required_documents or [])
        optional = _documents.validate_python(process.optional_documents or [])
        fields = _fields.validate_python(process.required_fields or [])
        field_order = {spec.key: index for index, spec in enumerate(fields)}

        drawers: list[TemplateDrawer] = []
        sources: dict[str, list[TemplateFieldSource]] = {}
        for spec, needed in [(item, True) for item in required] + [(item, False) for item in optional]:
            label = spec.label_he or spec.label
            reads: list[str] = []
            if spec.reading is not None and spec.reading.enabled:
                for rule in spec.reading.rules:
                    if rule.slot_key in field_order and rule.slot_key not in reads:
                        reads.append(rule.slot_key)
            reads.sort(key=lambda key: field_order[key])
            for key in reads:
                sources.setdefault(key, []).append(
                    TemplateFieldSource(drawer_id=spec.type_key, label_he=_SOURCE_HE.get(spec.type_key, label))
                )
            drawers.append(
                TemplateDrawer(
                    id=spec.type_key,
                    label_he=label,
                    accepted_document_types=[spec.type_key],
                    required=needed,
                    reads_fields=reads,
                )
            )

        path = await asyncio.to_thread(default_template_path, process, settings)
        available = path.is_file()
        blank = await asyncio.to_thread(_fills_blank, process, settings)
        targets = await _targets(process, path, available, blank)
        sections = (layout.get("flat_form") or {}).get("slot_section") or {}
        mapped = [
            TemplateField(
                key=spec.key,
                label_he=spec.label_he or spec.label,
                field_type=spec.field_type,
                required=spec.required,
                sources=sources.get(spec.key, []),
                target=TemplateFieldTarget(
                    page=targets[spec.key][0] if spec.key in targets else None,
                    mode=targets[spec.key][1] if spec.key in targets else None,  # type: ignore[arg-type]
                    section_he=sections.get(spec.key) or (spec.provenance.section_he if spec.provenance else None),
                ),
            )
            for spec in fields
        ]
        title, description = _TEXT_HE.get(process.key, (process.name, process.description))
        total, signed = totals.get(process.id, [0, 0])
        result.append(
            TemplateRead(
                process_type=process.key,
                title_he=title,
                description_he=description,
                form_source="official_blank" if blank else "generated",
                default_template_available=available,
                required_drawers=drawers,
                mapped_fields=mapped,
                case_counts=TemplateCaseCounts(total=total, filling=total - signed, signed=signed),
            )
        )
    return result
