import re
from dataclasses import dataclass
from datetime import datetime

from app.schemas.process import FieldSpec

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y")


@dataclass(frozen=True)
class FieldValidation:
    ok: bool
    normalized: str = ""
    message: str = ""


def missing_required_fields(specs: list[FieldSpec], values: dict[str, str]) -> list[FieldSpec]:
    missing: list[FieldSpec] = []
    for spec in specs:
        if spec.required and not str(values.get(spec.key, "")).strip():
            missing.append(spec)
    return missing


def validate_field(spec: FieldSpec, raw: str) -> FieldValidation:
    text = " ".join(raw.split())
    if not text or not any(character.isalnum() for character in text):
        return FieldValidation(False, message=f"Enter a value for {spec.label}.")
    if spec.field_type == "email":
        email = text.lower()
        if not _EMAIL.match(email):
            return FieldValidation(False, message=f"{spec.label} needs an address like name@example.com.")
        return FieldValidation(True, email)
    if spec.field_type == "phone":
        phone = _normalize_phone(text)
        if phone is None:
            return FieldValidation(False, message=f"{spec.label} needs 9 to 15 digits.")
        return FieldValidation(True, phone)
    if spec.field_type == "date":
        normalized = _normalize_date(text)
        if normalized is None:
            return FieldValidation(False, message=f"{spec.label} needs a date as YYYY-MM-DD or DD/MM/YYYY.")
        return FieldValidation(True, normalized)
    if spec.field_type == "id_number":
        normalized = normalize_israeli_id(text)
        if normalized is None:
            return FieldValidation(False, message=f"{spec.label} is not a valid 9-digit national ID.")
        return FieldValidation(True, normalized)
    # An optional detail such as a house number may be a single character.
    if len(text) < (2 if spec.required else 1):
        return FieldValidation(False, message=f"{spec.label} is too short.")
    if len(text) > 200:
        return FieldValidation(False, message=f"{spec.label} is too long.")
    return FieldValidation(True, text)


def normalize_israeli_id(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if not digits or len(digits) > 9:
        return None
    padded = digits.zfill(9)
    if padded == "000000000" or not _israeli_checksum(padded):
        return None
    return padded


def _israeli_checksum(padded: str) -> bool:
    total = 0
    for index, character in enumerate(padded):
        product = int(character) * (1 if index % 2 == 0 else 2)
        if product > 9:
            product = (product // 10) + (product % 10)
        total += product
    return total % 10 == 0


def _normalize_phone(raw: str) -> str | None:
    leading_plus = raw.strip().startswith("+")
    digits = re.sub(r"\D", "", raw)
    if not 9 <= len(digits) <= 15:
        return None
    return f"+{digits}" if leading_plus else digits


def _normalize_date(raw: str) -> str | None:
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None
