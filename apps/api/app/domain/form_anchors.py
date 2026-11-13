"""Bind AcroForm widgets in an uploaded PDF to the process's existing field slots.

A widget binds to a slot only through an exact pdf_field_name match or through
the closed synonym table below. Nothing here creates a new slot or a new
pdf_field_name, and a widget that does not bind is kept as an unbound anchor,
never turned into a question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.schemas.process import FieldSpec

AnchorMatch = Literal["exact", "synonym"]

# Closed list. Each synonym maps to exactly one existing slot key, and a key is
# used only when the case's process actually has that slot.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "full_name": ("name", "fullname", "full name", "applicant name", "שם", "שם מלא", "שם המבקש"),
    "national_id": (
        "id",
        "id number",
        "id no",
        "teudat zehut",
        "ת.ז",
        'ת"ז',
        "תז",
        "מספר זהות",
        "תעודת זהות",
        "מס זהות",
    ),
    "email": ("e-mail", "mail", "email address", "דואל", 'דוא"ל', "דואר אלקטרוני", "אימייל"),
    "phone": ("phone number", "mobile", "cell", "tel", "telephone", "טלפון", "נייד", "טלפון נייד"),
    "address_he": ("address", "home address", "כתובת", "כתובת מגורים"),
    "start_date": ("start date", "employment start", "תאריך תחילת עבודה", "תחילת עבודה"),
    "buyer_name": ("buyer", "purchaser", "שם הקונה", "קונה", "רוכש"),
    "seller_name": ("seller", "vendor", "שם המוכר", "מוכר"),
    "property_address_he": ("property address", "כתובת הנכס"),
    "parcel_number": ("parcel", "gush helka", "גוש חלקה", "גוש", "חלקה"),
    "price": ("purchase price", "consideration", "מחיר", "תמורה"),
    "contract_date": ("contract date", "agreement date", "תאריך החוזה", "תאריך ההסכם"),
    "first_name": ("שם פרטי",),
    "last_name": ("שם משפחה",),
    "city": ("עיר", "ישוב", "יישוב"),
    "street": ("רחוב",),
    "bank_name": ("בנק",),
    "bank_branch": ("סניף",),
    "bank_account": ("חשבון", "מס חשבון"),
}

_SEPARATORS = re.compile(r"[\s_\-./:]+")


def normalize(name: str) -> str:
    """Lowercase and collapse separators, so "Full_Name" and "full name" compare equal."""
    return _SEPARATORS.sub(" ", name.strip().lower()).strip()


def _synonym_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for key, words in SYNONYMS.items():
        for word in (key, *words):
            normalized = normalize(word)
            existing = index.get(normalized)
            if existing is not None and existing != key:
                raise RuntimeError(f"Synonym {word!r} maps to both {existing!r} and {key!r}.")
            index[normalized] = key
    return index


SYNONYM_INDEX = _synonym_index()


@dataclass(frozen=True)
class SlotBinding:
    key: str
    match: AnchorMatch


def bind_widget(field_name: str, fields: list[FieldSpec]) -> SlotBinding | None:
    """Return the slot this widget fills, or None when it must stay unbound."""
    for spec in fields:
        if field_name == spec.pdf_field_name:
            return SlotBinding(spec.key, "exact")
    key = SYNONYM_INDEX.get(normalize(field_name))
    if key is None:
        return None
    if any(spec.key == key for spec in fields):
        return SlotBinding(key, "synonym")
    return None
