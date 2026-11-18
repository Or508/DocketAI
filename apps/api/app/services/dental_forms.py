"""Draw the dental clinic's blank forms: one cell per slot, then the patient's declaration and signature.

The same flat two-page layout as the drawn Form 101 and the real estate form. Each cell carries
its slot's Hebrew label, which is how the filled value finds its cell. The declarations are a
starting template; each clinic approves its own wording with its legal adviser.
"""

from __future__ import annotations

from pathlib import Path

from app.catalog.dental import BOTOX, CT, PATIENT_SIGNATURE, QUESTIONNAIRE, TREATMENT_PLAN
from app.services.form101 import _LEFT, _RIGHT, _build

# Bump when a drawing changes, so a server redraws its copy.
DENTAL_FORMS_VERSION = 1

_PATIENT = (
    "פרטי המטופל",
    (
        (("שם המטופל", 300.0, _RIGHT, False), ("טלפון נייד", _LEFT, 290.0, False)),
        (("מספר זהות", 320.0, _RIGHT, True),),
    ),
)


def _pair(right: str, left: str):
    return ((right, 300.0, _RIGHT, False), (left, _LEFT, 290.0, False))


def _wide(label: str):
    return ((label, _LEFT, _RIGHT, False),)


# process key -> (title, subtitle, sections, declaration title, declaration lines)
_FORMS = {
    TREATMENT_PLAN: (
        "הסכמה לתוכנית טיפול",
        "תוכנית טיפול והצעת מחיר",
        (
            _PATIENT,
            ("תוכנית הטיפול", (_wide("תוכנית הטיפול"), _pair("מחיר כולל", "תנאי תשלום"), _pair("הרופא המטפל", "תאריך התוכנית"))),
        ),
        "הצהרת המטופל",
        (
            "הרופא המטפל הציג לי את תוכנית הטיפול, את מטרתה ואת החלופות לה.",
            "הוסבר לי כי שינוי בתוכנית במהלך הטיפול עשוי לשנות את המחיר, ויוצג לי לאישור.",
            "קראתי את הצעת המחיר ואת תנאי התשלום ואני מאשר/ת אותם.",
            "ניתנה לי הזדמנות לשאול שאלות, ואני מסכים/ה לתוכנית מרצוני.",
        ),
    ),
    QUESTIONNAIRE: (
        "שאלון רפואי",
        "מידע רפואי לפני טיפול שיניים",
        (
            _PATIENT,
            ("פרטים רפואיים", (_pair("תאריך לידה", "הריון או הנקה"), _wide("תרופות קבועות"), _wide("אלרגיות"), _wide("מחלות רקע"))),
        ),
        "הצהרת המטופל",
        (
            "המידע שמסרתי בשאלון זה מלא ונכון.",
            "ידוע לי כי מידע חסר או שגוי עלול להשפיע על בטיחות הטיפול.",
            "אעדכן את המרפאה על כל שינוי במצבי הרפואי או בתרופות שאני נוטל/ת.",
        ),
    ),
    BOTOX: (
        "הסכמה מדעת להזרקת בוטוקס",
        "טיפול ברעלן בוטולינום",
        (
            _PATIENT,
            ("פרטי הטיפול", (_wide("אזור הטיפול"), _pair("שם התכשיר", "מספר יחידות"), _pair("הרופא המטפל", "תאריך הטיפול"))),
        ),
        "הצהרת המטופל",
        (
            "הרופא המטפל הסביר לי את מהות הטיפול, את מטרתו ואת החלופות לו.",
            "הוסבר לי כי השפעת הטיפול זמנית ועשויה להשתנות בין אדם לאדם.",
            "הוסברו לי תופעות לוואי אפשריות: כאב, נפיחות או שטף דם במקום ההזרקה,",
            "כאב ראש, צניחה זמנית של העפעף, אסימטריה ותגובה אלרגית.",
            "הצהרתי שאינני בהריון או מניקה, ומסרתי את כל המידע על מצבי הרפואי.",
            "ניתנה לי הזדמנות לשאול שאלות, ואני מסכים/ה לטיפול מרצוני.",
        ),
    ),
    CT: (
        "הסכמה לצילום CT",
        "צילום CT דנטלי (CBCT)",
        (
            _PATIENT,
            ("פרטי הצילום", (_wide("אזור הצילום"), _pair("הרופא המפנה", "תאריך הצילום"))),
        ),
        "הצהרת המטופל",
        (
            "הוסברו לי מטרת הצילום והמידע שהוא נותן לתכנון הטיפול.",
            "הוסבר לי כי הצילום כרוך בחשיפה לקרינה מייננת במינון נמוך.",
            "הצהרתי אם אני בהריון או עשויה להיות בהריון.",
            "ניתנה לי הזדמנות לשאול שאלות, ואני מסכים/ה לביצוע הצילום.",
        ),
    ),
}


def dental_form_builder(process_key: str):
    """A builder for this process's blank (font path -> PDF bytes), or None if it is not a dental form."""
    if process_key not in _FORMS:
        return None
    title, subtitle, sections, declaration_title, declaration = _FORMS[process_key]

    def build(font_path: Path) -> bytes:
        return _build(
            font_path,
            sections,
            f"{process_key} (blank)",
            title=title,
            subtitle=subtitle,
            declaration_title=declaration_title,
            declaration=declaration,
            signature_label=PATIENT_SIGNATURE,
            creator=f"dental-forms v{DENTAL_FORMS_VERSION}",
        )

    return build
