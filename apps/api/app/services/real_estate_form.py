"""Draw the blank real estate transaction form this server offers when the office has none.

The same flat, two-page layout as the drawn Form 101: one cell per slot on the first page,
the buyer's declaration and one signature cell on the second. Same inputs, same bytes.
"""

from __future__ import annotations

from pathlib import Path

from app.services.form101 import _LEFT, _RIGHT, _build

# Bump when the drawing changes, so a server redraws its copy.
REAL_ESTATE_FORM_VERSION = 1
REAL_ESTATE_TITLE = "עסקת מקרקעין"
REAL_ESTATE_SUBTITLE = "טופס פרטי העסקה והצהרת הרוכש"
REAL_ESTATE_SIGNATURE_LABEL = "חתימת הרוכש"

_SECTIONS = (
    (
        "פרטי הצדדים",
        (
            (
                ("שם הרוכש", 300.0, _RIGHT, False),
                ("שם המוכר", _LEFT, 290.0, False),
            ),
        ),
    ),
    (
        "פרטי הנכס",
        (
            (("כתובת הנכס", _LEFT, _RIGHT, False),),
            (("גוש וחלקה", 300.0, _RIGHT, False),),
        ),
    ),
    (
        "פרטי העסקה",
        (
            (
                ("מחיר", 300.0, _RIGHT, False),
                ("תאריך חוזה", _LEFT, 290.0, False),
            ),
        ),
    ),
)

_DECLARATION = (
    "אני מצהיר/ה כי פרטי העסקה שנמסרו בטופס זה הם מלאים ונכונים.",
    "ידוע לי כי הפרטים ישמשו לדיווח על העסקה לרשויות המס ולרישום הזכויות בנכס.",
    "אני מתחייב/ת להודיע למשרד על כל שינוי בפרטי העסקה עד למועד השלמתה.",
)


def build_real_estate_form(font_path: Path) -> bytes:
    return _build(
        font_path,
        _SECTIONS,
        "Real estate transaction form (blank)",
        title=REAL_ESTATE_TITLE,
        subtitle=REAL_ESTATE_SUBTITLE,
        declaration_title="הצהרת הרוכש",
        declaration=_DECLARATION,
        signature_label=REAL_ESTATE_SIGNATURE_LABEL,
        creator=f"real-estate-form v{REAL_ESTATE_FORM_VERSION}",
    )
