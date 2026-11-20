"""Build the sample documents a visitor can download and run through a Form 101 case.

Every detail is invented, and each page says so. The text layer is real Hebrew in logical order,
so the office's document reader fills the form from these files exactly as from a real bundle.

    python scripts/demo_documents.py            # writes apps/web/public/demo/*.pdf
    python scripts/demo_documents.py OUT_DIR
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pymupdf

API_ROOT = Path(__file__).resolve().parents[1]
FONT = API_ROOT / "app" / "assets" / "fonts" / "Rubik-Regular.ttf"
DEFAULT_OUT = API_ROOT.parent / "web" / "public" / "demo"

# One invented employee. 100000009 passes the Israeli ID checksum and belongs to no one.
PERSON = {
    "first_name": "דנה",
    "last_name": "כהן",
    "national_id": "100000009",
    "street": "הרצל",
    "house_number": "15",
    "city": "תל אביב",
    "bank_name": "לאומי",
    "bank_branch": "800",
    "bank_account": "456789",
}

_CSS = """
* { font-family: rubik; }
body { direction: rtl; color: #1b1a17; font-size: 12pt; }
.bar { background: #0e4f49; color: white; padding: 10pt 14pt; font-size: 15pt; font-weight: bold; }
.sub { color: #67625a; font-size: 10pt; margin: 6pt 0 14pt 0; }
.stamp { border: 1.5pt solid #a03a22; color: #a03a22; padding: 6pt 10pt; font-size: 10.5pt; margin-bottom: 14pt; }
p.row { border-bottom: 0.6pt solid #e4e2dc; padding: 7pt 4pt; margin: 0; }
span.k { color: #67625a; }
.foot { color: #67625a; font-size: 9pt; margin-top: 18pt; }
"""


@dataclass(frozen=True)
class Sample:
    filename: str
    title: str
    issuer: str
    rows: list[tuple[str, str]]
    note: str  # shown on the web page, never printed in the PDF


SAMPLES = [
    Sample(
        filename="01-teudat-zehut.pdf",
        title="צילום תעודת זהות",
        issuer="רשות האוכלוסין וההגירה · דוגמה",
        rows=[
            ("שם פרטי:", PERSON["first_name"]),
            ("שם משפחה:", PERSON["last_name"]),
            ("מספר זהות:", PERSON["national_id"]),
            ("תאריך לידה:", "01/01/1990"),
            ("מין:", "נקבה"),
        ],
        note="המערכת מזהה כאן את השם ואת מספר הזהות, ובודקת את ספרת הביקורת.",
    ),
    Sample(
        filename="02-arnona.pdf",
        title="חשבון ארנונה דו-חודשי",
        issuer="מנהל הארנונה · דוגמה",
        rows=[
            ("שם המחזיק:", f"{PERSON['first_name']} {PERSON['last_name']}"),
            ("רחוב:", PERSON["street"]),
            ("מס' בית:", PERSON["house_number"]),
            ("עיר:", PERSON["city"]),
            ("תקופת חיוב:", "ספטמבר–אוקטובר 2026"),
            ("סכום לתשלום:", "₪ 1,240.00"),
        ],
        note="המערכת לוקחת מכאן את כתובת המגורים לטופס.",
    ),
    Sample(
        filename="03-ishur-bank.pdf",
        title="אישור ניהול חשבון",
        issuer="הופק לבקשת הלקוח · דוגמה",
        rows=[
            ("שם בעל החשבון:", f"{PERSON['first_name']} {PERSON['last_name']}"),
            ("שם הבנק:", PERSON["bank_name"]),
            ("מספר סניף:", PERSON["bank_branch"]),
            ("מספר חשבון:", PERSON["bank_account"]),
        ],
        note="המערכת ממלאת מכאן את פרטי הבנק להעברת המשכורת.",
    ),
]


def _html(sample: Sample) -> str:
    # One line per detail, label then value, the way the office's reader expects a printed form.
    rows = "".join(f"<p class='row'><span class='k'>{key}</span> {value}</p>" for key, value in sample.rows)
    return (
        f"<div class='bar'>{sample.title}</div>"
        f"<div class='sub'>{sample.issuer}</div>"
        "<div class='stamp'>מסמך לדוגמה בלבד. כל הפרטים בדויים ואינם שייכים לאדם אמיתי.</div>"
        f"{rows}"
        "<div class='foot'>נוצר עבור הדגמה של DocketFlow</div>"
    )


def build(sample: Sample) -> bytes:
    archive = pymupdf.Archive(str(FONT.parent))
    css = f"@font-face {{ font-family: rubik; src: url({FONT.name}); }}" + _CSS
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_htmlbox(pymupdf.Rect(48, 48, 547, 794), _html(sample), css=css, archive=archive)
    document.set_metadata({"title": f"{sample.title} (דוגמה)", "producer": "DocketFlow demo"})
    data = document.tobytes(garbage=3, deflate=True)
    document.close()
    return data


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for sample in SAMPLES:
        (out / sample.filename).write_bytes(build(sample))
        print(out / sample.filename)


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT)
