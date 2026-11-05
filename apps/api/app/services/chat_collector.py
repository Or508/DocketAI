import logging

from app.domain.classification import FieldHit
from app.schemas.process import FieldSpec
from app.services.field_validator import FieldValidation, missing_required_fields, validate_field
from app.services.gemini_client import GeminiClient

logger = logging.getLogger(__name__)

OPENING = (
    "Upload the bundle when you are ready. "
    "I will record the personal details the form needs, one checked value at a time."
)


class ChatCollector:
    """Slot-filling clerk. Gemini extracts fields when configured; otherwise the next empty field takes the message."""

    def __init__(self, gemini: GeminiClient) -> None:
        self._gemini = gemini

    async def respond(
        self,
        *,
        fields: list[FieldSpec],
        values: dict[str, str],
        message: str,
    ) -> tuple[dict[str, str], str]:
        updated = dict(values)
        extracted, used_model = await self._extract(message, fields)
        errors: list[str] = []
        accepted: list[str] = []
        by_key = {item.key: item for item in fields}

        if not extracted and not used_model:
            pending = missing_required_fields(fields, updated)
            if pending:
                extracted = [FieldHit(key=pending[0].key, value=message)]

        for hit in extracted:
            spec = by_key.get(hit.key)
            if spec is None:
                continue
            result: FieldValidation = validate_field(spec, hit.value)
            if not result.ok:
                errors.append(result.message)
                continue
            updated[spec.key] = result.normalized
            accepted.append(spec.label)

        still_missing = missing_required_fields(fields, updated)
        reply = _reply(accepted, errors, still_missing)
        return updated, reply

    async def _extract(self, message: str, fields: list[FieldSpec]) -> tuple[list[FieldHit], bool]:
        try:
            parsed = await self._gemini.extract_fields(message=message, fields=fields)
        except Exception:
            logger.info("Field extraction fell back to the next empty field")
            return [], False
        hits = [item for item in parsed.fields if item.key and item.value.strip()]
        return hits, True


def ask(field: FieldSpec) -> str:
    hints = {
        "email": "Use the form name@example.com.",
        "phone": "Include the area code.",
        "date": "Use YYYY-MM-DD or DD/MM/YYYY.",
        "id_number": "Enter up to 9 digits; a leading zero is added when needed.",
        "text": "",
    }
    hebrew = f" ({field.label_he})" if field.label_he else ""
    hint = hints[field.field_type]
    question = f"What is the {field.label}{hebrew}?"
    return f"{question} {hint}".strip()


def _reply(accepted: list[str], errors: list[str], missing: list[FieldSpec]) -> str:
    parts: list[str] = []
    if accepted:
        parts.append("Recorded " + ", ".join(accepted) + ".")
    if errors:
        parts.append(" ".join(errors))
    if missing:
        parts.append(ask(missing[0]))
    elif not errors:
        parts.append("All required details are in. You can sign once every required document is on the checklist.")
    elif not parts:
        parts.append(ask(missing[0]) if missing else "I could not use that value.")
    return " ".join(parts)
