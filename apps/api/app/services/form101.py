"""Draw the blank Form 101 this server offers when the office has not supplied its own.

A flat, two-page Hebrew form: one drawn cell per slot under its section title, digit
boxes for the ID number, and one signature cell on the declaration page. It carries
no widgets, so it is anchored, filled and signed exactly like an uploaded official form.
The same inputs always give the same bytes.
"""

from __future__ import annotations

from pathlib import Path

import fitz

from app.domain.text_layout import shape_for_pdf
from app.services.pdf_filler import _pin_dates, _stable_id

# Bump when the drawing changes, so a server redraws its copy.
FORM_101_VERSION = 1
FORM_101_TITLE = "טופס 101"
FORM_101_SUBTITLE = "כרטיס עובד ובקשה להקלה ולתיאום מס"
SIGNATURE_LABEL = "חתימת העובד"

_WIDTH, _HEIGHT = 595.0, 842.0
_RIGHT = 540.0
_LEFT = 55.0
_INK = (0.11, 0.1, 0.08)
_TIDE = (0.04, 0.23, 0.22)
_RULE = (0.35, 0.33, 0.3)
_CELL_HEIGHT = 40.0
_ID_DIGITS = 9
_DIGIT_WIDTH = 18.0

# (section title, rows); a row is cells from right to left as (label, x0, x1, digit boxes).
_SECTIONS: tuple[tuple[str, tuple[tuple[tuple[str, float, float, bool], ...], ...]], ...] = (
    (
        "פרטי העובד",
        (
            (
                ("מספר זהות", 320.0, _RIGHT, True),
                ("שם פרטי", 190.0, 310.0, False),
                ("שם משפחה", _LEFT, 180.0, False),
            ),
        ),
    ),
    (
        "כתובת מגורים ופרטי התקשרות",
        (
            (
                ("רחוב", 300.0, _RIGHT, False),
                ("מס' בית", 200.0, 290.0, False),
                ("יישוב", _LEFT, 190.0, False),
            ),
            (("טלפון נייד", 300.0, _RIGHT, False),),
        ),
    ),
    (
        "פרטי חשבון הבנק",
        (
            (
                ("שם הבנק", 300.0, _RIGHT, False),
                ("מס' סניף", 200.0, 290.0, False),
                ("מספר חשבון", _LEFT, 190.0, False),
            ),
        ),
    ),
)

# The same card for the plain onboarding process: its six slots, one cell each.
_ONBOARDING_SECTIONS: tuple[tuple[str, tuple[tuple[tuple[str, float, float, bool], ...], ...]], ...] = (
    (
        "פרטי העובד",
        (
            (
                ("מספר זהות", 320.0, _RIGHT, True),
                ("שם מלא", _LEFT, 310.0, False),
            ),
        ),
    ),
    (
        "מען ופרטי התקשרות",
        (
            (("כתובת", _LEFT, _RIGHT, False),),
            (
                ("טלפון נייד", 300.0, _RIGHT, False),
                ("דואר אלקטרוני", _LEFT, 290.0, False),
            ),
        ),
    ),
    (
        "פרטי ההעסקה",
        ((("תאריך תחילת עבודה", 300.0, _RIGHT, False),),),
    ),
)

_DECLARATION = (
    "אני מצהיר/ה כי כל הפרטים שמסרתי בטופס זה הם מלאים ונכונים.",
    "ידוע לי כי מסירת פרטים שאינם נכונים או השמטתם היא עבירה על פקודת מס הכנסה.",
    "אני מתחייב/ת להודיע למעסיק על כל שינוי שיחול בפרטים שמסרתי בתוך שבוע ימים.",
)


def build_form_101(font_path: Path) -> bytes:
    """The employee card with split name, address and bank cells."""
    return _build(font_path, _SECTIONS, "Form 101 employee card (blank)")


def build_onboarding_form_101(font_path: Path) -> bytes:
    """The employee card that carries the onboarding process's own six slots."""
    return _build(font_path, _ONBOARDING_SECTIONS, "Form 101 new employee card (blank)")


def _build(
    font_path: Path,
    sections,
    title_en: str,
    *,
    title: str = FORM_101_TITLE,
    subtitle: str = FORM_101_SUBTITLE,
    declaration_title: str = "הצהרת העובד",
    declaration: tuple[str, ...] | None = None,
    signature_label: str = SIGNATURE_LABEL,
    creator: str = f"form101 v{FORM_101_VERSION}",
) -> bytes:
    """Draw a two-page flat form: the cells on the first page, the declaration and signature on the second."""
    document = fitz.open()
    try:
        font = fitz.Font(fontfile=str(font_path))

        def text(page, right: float, baseline: float, value: str, size: float, color=_INK) -> None:
            shown = shape_for_pdf(value)
            width = font.text_length(shown, fontsize=size)
            page.insert_text((right - width, baseline), shown, fontname="rubik", fontsize=size, color=color)

        def heading(page, top: float) -> float:
            text(page, _RIGHT, top + 18, title, 18, _TIDE)
            text(page, _RIGHT, top + 36, subtitle, 11)
            page.draw_line((_LEFT, top + 46), (_RIGHT, top + 46), color=_TIDE, width=1.2)
            return top + 64

        first = document.new_page(width=_WIDTH, height=_HEIGHT)
        first.insert_font(fontname="rubik", fontfile=str(font_path))
        top = heading(first, 44.0)
        for title, rows in sections:
            text(first, _RIGHT, top + 10, title, 10.5, _TIDE)
            top += 20
            for row in rows:
                for label, x0, x1, digits in row:
                    first.draw_rect(fitz.Rect(x0, top, x1, top + _CELL_HEIGHT), color=_RULE, width=0.7)
                    text(first, x1 - 5, top + 10.5, label, 8)
                    if digits:
                        bottom = top + _CELL_HEIGHT
                        start = x0 + 12
                        for index in range(_ID_DIGITS + 1):
                            x = start + index * _DIGIT_WIDTH
                            first.draw_line((x, bottom - 14), (x, bottom), color=_RULE, width=0.6)
                top += _CELL_HEIGHT + 8
            top += 10

        second = document.new_page(width=_WIDTH, height=_HEIGHT)
        second.insert_font(fontname="rubik", fontfile=str(font_path))
        top = heading(second, 44.0)
        text(second, _RIGHT, top + 10, declaration_title, 10.5, _TIDE)
        top += 34
        for line in declaration or _DECLARATION:
            text(second, _RIGHT, top, line, 10)
            top += 18
        top += 22
        second.draw_rect(fitz.Rect(330, top, _RIGHT, top + 72), color=_RULE, width=0.9)
        text(second, _RIGHT - 5, top + 10.5, signature_label, 8)
        second.draw_rect(fitz.Rect(190, top, 320, top + 72), color=_RULE, width=0.7)
        text(second, 315, top + 10.5, "תאריך", 8)

        document.set_metadata(
            {
                "title": title_en,
                "author": "DocketAI",
                "producer": "DocketAI",
                "creator": creator,
            }
        )
        _pin_dates(document)
        return _stable_id(document.tobytes(garbage=4, deflate=True))
    finally:
        document.close()
