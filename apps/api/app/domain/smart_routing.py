"""Decide which drawer a dropped file belongs in, from its name and its text alone.

No model is asked. A file is routed only when one document type clearly leads; a tie or
no evidence leaves the file to the ordinary classifier and the office.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MatchedBy = Literal["filename", "content", "filename_and_content"]

_NAME_WEIGHT = 4
_STRONG = 3
_WEAK = 1


@dataclass(frozen=True)
class _Signals:
    # Whole Latin words in the file name, and Hebrew fragments anywhere in it.
    name_words: tuple[str, ...] = ()
    name_parts: tuple[str, ...] = ()
    # Phrases that all but name the document, and words that only lean toward it.
    strong: tuple[str, ...] = ()
    weak: tuple[str, ...] = ()


_SIGNALS: dict[str, _Signals] = {
    "id_copy": _Signals(
        name_words=("id", "tz", "teuda", "teudat", "zehut", "passport", "identity"),
        name_parts=("זהות", "תז", "ת.ז", "דרכון"),
        strong=("תעודת זהות", "תעודת הזהות", "משרד הפנים", "identity card", "passport", "דרכון"),
        weak=("שם פרטי", "שם משפחה", "תאריך לידה", "date of birth"),
    ),
    "proof_of_address": _Signals(
        name_words=("arnona", "address", "utility", "bill", "electricity", "water"),
        name_parts=("ארנונה", "כתובת", "חשמל", "מים"),
        strong=("ארנונה", "חשבון חשמל", "אישור תושב", "municipal tax", "utility bill"),
        weak=("עירייה", "עיריית", "רחוב", "מען", "נכס"),
    ),
    "bank_confirmation": _Signals(
        name_words=("bank", "iban", "account", "check", "cheque"),
        name_parts=("בנק", "חשבון בנק", "ניהול חשבון", "שיק"),
        strong=("אישור ניהול חשבון", "ניהול חשבון", "שם הבנק", "iban", "account ownership", "voided check"),
        weak=("בנק", "סניף", "מספר חשבון", "bank"),
    ),
    "tax_form": _Signals(
        name_words=("tax", "101", "form101"),
        name_parts=("101", "מס הכנסה"),
        strong=("טופס 101", "כרטיס עובד", "form 101", "tax withholding"),
        weak=("תיאום מס", "מס הכנסה", "מעסיק"),
    ),
    "pension_form": _Signals(
        name_words=("pension",),
        name_parts=("פנסיה", "גמל"),
        strong=("קרן פנסיה", "קופת גמל", "pension fund"),
        weak=("פנסיה", "pension"),
    ),
    "purchase_agreement": _Signals(
        name_words=("agreement", "contract", "purchase"),
        name_parts=("הסכם", "חוזה"),
        strong=("הסכם מכר", "חוזה מכר", "purchase agreement", "sale agreement"),
        weak=("המוכר", "הקונה", "הרוכש", "התמורה"),
    ),
    "title_deed": _Signals(
        name_words=("tabu", "taboo", "deed", "nesach"),
        name_parts=("נסח", "טאבו"),
        strong=("נסח טאבו", "לשכת רישום המקרקעין", "נסח רישום", "title deed", "land registry"),
        weak=("גוש", "חלקה", "טאבו"),
    ),
    "tax_clearance": _Signals(
        name_words=("clearance",),
        name_parts=("אישור מס", "מס שבח", "מס רכישה"),
        strong=("מס שבח", "מס רכישה", "אישור מסים", "tax clearance"),
        weak=("רשות המסים", "אישור מס"),
    ),
    "appraisal": _Signals(
        name_words=("appraisal", "valuation"),
        name_parts=("שמאות", "שמאי"),
        strong=("חוות דעת שמאי", "שמאי מקרקעין", "appraisal report"),
        weak=("שמאות", "שמאי", "שווי"),
    ),
    "mortgage_approval": _Signals(
        name_words=("mortgage", "loan"),
        name_parts=("משכנתא", "משכנתה"),
        strong=("אישור עקרוני", "הלוואת משכנתא", "הלוואת משכנתה", "mortgage approval"),
        weak=("משכנתא", "משכנתה", "הלוואה", "mortgage"),
    ),
}

_WORD = re.compile(r"[a-z0-9]+")
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Route:
    document_type: str
    matched_by: MatchedBy


def route_document(filename: str, text: str, allowed: list[str]) -> Route | None:
    """The one document type this file clearly is, among those the process takes, or None."""
    name = filename.lower()
    words = set(_WORD.findall(name))
    body = _SPACE.sub(" ", text.lower())
    # Some PDFs hand back Hebrew in visual order; a phrase counts either way round.
    mirrored = body[::-1]

    scored: list[tuple[int, str, MatchedBy]] = []
    for key in allowed:
        signals = _SIGNALS.get(key)
        if signals is None:
            continue
        by_name = sum(_NAME_WEIGHT for word in signals.name_words if word in words)
        by_name += sum(_NAME_WEIGHT for part in signals.name_parts if part in name)
        by_text = sum(_STRONG for phrase in signals.strong if phrase in body or phrase in mirrored)
        by_text += sum(_WEAK for phrase in signals.weak if phrase in body or phrase in mirrored)
        if by_name + by_text == 0:
            continue
        matched: MatchedBy = "filename_and_content" if by_name and by_text else "filename" if by_name else "content"
        scored.append((by_name + by_text, key, matched))
    if not scored:
        return None
    scored.sort(reverse=True)
    best = scored[0]
    # One weak word proves nothing, and neither does a lead shared with another type.
    if best[0] < 2 or (len(scored) > 1 and scored[1][0] == best[0]):
        return None
    return Route(document_type=best[1], matched_by=best[2])
