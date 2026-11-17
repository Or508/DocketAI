"""The compliance report of one case: is the form on it, are its drawers and fields full,
is the ID number sound, and do its documents agree with each other.

Everything here is a plain rule over what the case already holds. The same case always
gives the same report. Detail lines name fields and drawers, never a person's values.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.schemas.integrity import IntegrityCheck

# The documents that describe the person, and so can contradict each other.
CROSS_CHECKED = ("id_copy", "proof_of_address", "bank_confirmation")
ID_KEYS = ("national_id", "id_number")
_IDENTITY_SLOTS = {"national_id", "id_number", "first_name", "last_name", "full_name", "buyer_name"}
_NINE_DIGITS = re.compile(r"(?<!\d)\d{9}(?!\d)")
_WEIGHTS = {
    "target_form_loaded": 25,
    "required_drawers": 25,
    "national_id_checksum": 15,
    "cross_doc_consistency": 15,
    "required_fields_complete": 20,
}


def israeli_id_is_valid(raw: str) -> bool:
    """Nine digits (shorter numbers are padded on the left) whose check digit adds up."""
    digits = raw.strip()
    if not digits.isdigit() or len(digits) > 9:
        return False
    padded = digits.zfill(9)
    if padded == "000000000":
        return False
    total = 0
    for index, character in enumerate(padded):
        product = int(character) * (1 if index % 2 == 0 else 2)
        total += product if product < 10 else product - 9
    return total % 10 == 0


def ids_in_text(text: str) -> set[str]:
    """Every nine-digit run in the text that is a sound Israeli ID number."""
    return {match for match in _NINE_DIGITS.findall(text or "") if israeli_id_is_valid(match)}


@dataclass(frozen=True)
class FiledDocument:
    """A document that sits in one of the cross-checked drawers."""

    document_type: str
    label_he: str
    text: str
    # Slots this document reads differently from what the case holds, and whether its
    # reading was stopped because it names another person.
    conflicting_slots: tuple[str, ...] = ()
    id_mismatch: bool = False


@dataclass(frozen=True)
class CaseFacts:
    # None: no form on the case. Otherwise how many forms, and how many slots the first one has a place for.
    form_count: int
    form_bound: int
    # A process that signs only an uploaded form cannot be signed without one.
    form_required: bool
    missing_drawers: list[tuple[str, str]]  # (type key, Hebrew label)
    waiting_files: int
    required_drawer_count: int
    # (key, Hebrew label, has a value) for every required slot.
    required_fields: list[tuple[str, str, bool]]
    id_key: str | None
    id_value: str
    cross_checked_drawers: list[str]
    documents: list[FiledDocument] = field(default_factory=list)


def _form_check(facts: CaseFacts) -> IntegrityCheck:
    code, label = "target_form_loaded", "טופס היעד נטען"
    if facts.form_count == 1:
        return IntegrityCheck(
            code=code,
            label_he=label,
            status="pass",
            detail_he=f"הטופס נמצא בתיק, ו-{facts.form_bound} שדות אותרו עליו.",
        )
    if facts.form_count > 1:
        return IntegrityCheck(
            code=code,
            label_he=label,
            status="fail",
            detail_he=f"בתיק {facts.form_count} טפסים. יש להשאיר טופס אחד בלבד לפני החתימה.",
        )
    if facts.form_required:
        return IntegrityCheck(
            code=code, label_he=label, status="fail", detail_he="הטופס הריק לא נטען לתיק, ולכן אין על מה לחתום."
        )
    return IntegrityCheck(
        code=code,
        label_he=label,
        status="warn",
        detail_he="הטופס הריק לא נטען לתיק. החתימה תיעשה על התבנית המובנית של המערכת.",
    )


def _drawers_check(facts: CaseFacts) -> IntegrityCheck:
    code, label = "required_drawers", "מסמכי חובה במגירות"
    if facts.missing_drawers:
        names = ", ".join(name for _key, name in facts.missing_drawers)
        return IntegrityCheck(
            code=code,
            label_he=label,
            status="fail",
            detail_he=f"חסרים {len(facts.missing_drawers)} מתוך {facts.required_drawer_count} מסמכי חובה: {names}.",
            drawer_type=facts.missing_drawers[0][0],
        )
    if facts.waiting_files:
        return IntegrityCheck(
            code=code,
            label_he=label,
            status="warn",
            detail_he=f"כל מסמכי החובה בתיק, אך {facts.waiting_files} קבצים נוספים עדיין ממתינים לתיוק.",
        )
    return IntegrityCheck(
        code=code,
        label_he=label,
        status="pass",
        detail_he=f"כל {facts.required_drawer_count} מסמכי החובה נמצאים במגירות.",
    )


def _id_check(facts: CaseFacts) -> IntegrityCheck:
    code, label = "national_id_checksum", "ספרת ביקורת של מספר הזהות"
    if facts.id_key is None:
        return IntegrityCheck(code=code, label_he=label, status="pass", detail_he="בטופס זה אין שדה מספר זהות.")
    if not facts.id_value:
        return IntegrityCheck(
            code=code, label_he=label, status="warn", detail_he="מספר הזהות עדיין לא הוזן.", field_key=facts.id_key
        )
    if israeli_id_is_valid(facts.id_value):
        return IntegrityCheck(
            code=code, label_he=label, status="pass", detail_he="מספר הזהות תקין: 9 ספרות וספרת ביקורת נכונה.", field_key=facts.id_key
        )
    return IntegrityCheck(
        code=code,
        label_he=label,
        status="fail",
        detail_he="מספר הזהות אינו תקין: ספרת הביקורת אינה מתאימה.",
        field_key=facts.id_key,
    )


def _cross_check(facts: CaseFacts) -> IntegrityCheck:
    code, label = "cross_doc_consistency", "עקביות בין המסמכים"
    if len(facts.cross_checked_drawers) < 2:
        return IntegrityCheck(
            code=code, label_he=label, status="pass", detail_he="בתהליך זה אין שני מסמכים מזהים שניתן להצליב."
        )
    reference = facts.id_value if facts.id_value and israeli_id_is_valid(facts.id_value) else None
    found = [(document, ids_in_text(document.text)) for document in facts.documents]

    def failed(document: FiledDocument, detail: str, slot: str | None) -> IntegrityCheck:
        return IntegrityCheck(
            code=code,
            label_he=label,
            status="fail",
            detail_he=detail,
            field_key=slot,
            drawer_type=document.document_type,
        )

    id_slot = facts.id_key or "national_id"
    for document, numbers in found:
        if document.id_mismatch:
            return failed(document, f"המסמך ״{document.label_he}״ נושא מספר זהות של אדם אחר.", id_slot)
        if reference and numbers and reference.zfill(9) not in numbers:
            return failed(
                document, f"מספר הזהות שבמסמך ״{document.label_he}״ שונה ממספר הזהות שבתיק.", id_slot
            )
    carrying = [(document, numbers) for document, numbers in found if numbers]
    for index, (first, numbers) in enumerate(carrying):
        for second, others in carrying[index + 1 :]:
            if numbers.isdisjoint(others):
                return failed(
                    second,
                    f"מספר הזהות שבמסמך ״{second.label_he}״ שונה מזה שבמסמך ״{first.label_he}״.",
                    id_slot,
                )
    for document, _numbers in found:
        slots = [slot for slot in document.conflicting_slots if slot in _IDENTITY_SLOTS]
        if slots:
            what = "מספר הזהות" if slots[0] in ID_KEYS else "השם"
            return failed(document, f"{what} שבמסמך ״{document.label_he}״ סותר את מה שנקרא ממסמך אחר.", slots[0])

    if len(facts.documents) < 2:
        return IntegrityCheck(
            code=code,
            label_he=label,
            status="warn",
            detail_he="יש פחות משני מסמכים מזהים בתיק, ולכן אין עדיין מה להצליב.",
        )
    return IntegrityCheck(
        code=code,
        label_he=label,
        status="pass",
        detail_he=f"{len(facts.documents)} מסמכים הוצלבו ולא נמצאה סתירה במספר הזהות או בשם.",
    )


def _fields_check(facts: CaseFacts) -> tuple[IntegrityCheck, float]:
    code, label = "required_fields_complete", "שדות חובה מלאים"
    total = len(facts.required_fields)
    empty = [(key, name) for key, name, filled in facts.required_fields if not filled]
    done = total - len(empty)
    ratio = 1.0 if total == 0 else done / total
    if not empty:
        return (
            IntegrityCheck(code=code, label_he=label, status="pass", detail_he=f"כל {total} שדות החובה מלאים."),
            ratio,
        )
    names = ", ".join(name for _key, name in empty)
    return (
        IntegrityCheck(
            code=code,
            label_he=label,
            status="warn",
            detail_he=f"{done} מתוך {total} שדות חובה מלאים. חסרים: {names}.",
            field_key=empty[0][0],
        ),
        ratio,
    )


def run_checks(facts: CaseFacts) -> tuple[str, int, list[IntegrityCheck]]:
    """The checks in a fixed order, the overall verdict, and a score from 0 to 100."""
    fields, ratio = _fields_check(facts)
    checks = [_form_check(facts), _drawers_check(facts), _id_check(facts), _cross_check(facts), fields]
    earned = 0.0
    for check in checks:
        weight = _WEIGHTS[check.code]
        if check.code == "required_fields_complete":
            earned += weight * ratio
        elif check.status == "pass":
            earned += weight
        elif check.status == "warn":
            earned += weight / 2
    statuses = {check.status for check in checks}
    verdict = "block" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
    return verdict, int(round(earned)), checks
