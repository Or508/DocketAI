"""The private dental clinic's paperwork: consents and the medical questionnaire.

Each process fills a form this server draws (dental_forms.py): the patient's details read from
the ID card, the treatment details the clinic types, and the patient signs through the link.
The wording is a starting template. Each clinic approves its own text with its legal adviser.
"""

from __future__ import annotations

from app.domain.geometry import signature_rect

PATIENT_SIGNATURE = "חתימת המטופל"

# One key per process; the four drawn forms and the catalog text are keyed the same way.
BOTOX = "dental_botox_consent"
CT = "dental_ct_consent"
TREATMENT_PLAN = "dental_treatment_plan"
QUESTIONNAIRE = "dental_medical_questionnaire"
DENTAL_KEYS = (TREATMENT_PLAN, QUESTIONNAIRE, BOTOX, CT)

_PATIENT = ("פרטי המטופל", "patient details")


def _slot(
    key: str,
    label: str,
    label_he: str,
    field_type: str,
    rtl: bool,
    form: tuple[str, str],
    section: tuple[str, str],
    purpose_he: str,
    purpose_en: str,
    *,
    required: bool = True,
) -> dict:
    return {
        "key": key,
        "label": label,
        "label_he": label_he,
        "field_type": field_type,
        "pdf_field_name": key,
        "required": required,
        "rtl": rtl,
        "provenance": {
            "form_he": form[0],
            "form_en": form[1],
            "section_he": section[0],
            "section_en": section[1],
            "purpose_he": purpose_he,
            "purpose_en": purpose_en,
        },
    }


def _patient_slots(form: tuple[str, str]) -> list[dict]:
    return [
        _slot("patient_name", "Patient name", "שם המטופל", "text", True, form, _PATIENT,
              "השם מזהה את המטופל בטופס.", "The name identifies the patient on the form."),
        _slot("national_id", "National ID", "מספר זהות", "id_number", False, form, _PATIENT,
              "מספר הזהות מזהה את המטופל בתיק הרפואי.", "The ID number identifies the patient in the medical record."),
        _slot("phone", "Phone", "טלפון נייד", "phone", False, form, _PATIENT,
              "הטלפון משמש את המרפאה ליצירת קשר.", "The clinic uses the phone to reach the patient."),
    ]


def _id_card() -> dict:
    """The patient's ID card: the name and ID number are read from it."""
    return {
        "type_key": "id_copy",
        "label": "Patient ID",
        "label_he": "תעודת זהות",
        "description": "Government-issued identity card or passport bio page with a photo, given name, family name, and ID number.",
        "min_count": 1,
        "reading": {
            "enabled": True,
            "one_person": True,
            "rules": [
                {
                    "kind": "composite",
                    "slot_key": "patient_name",
                    "parts": [
                        {"labels": ["שם פרטי", "השם הפרטי", "first name", "given name"]},
                        {"labels": ["שם משפחה", "שם המשפחה", "last name", "family name", "surname"]},
                    ],
                },
                {"kind": "labeled", "slot_key": "national_id", "labels": ["מספר הזהות", "מספר זהות", "id number"]},
                {"kind": "unique", "slot_key": "national_id"},
            ],
        },
    }


def _layout() -> dict:
    # Signs the drawn consent loaded onto the case, else the generated template.
    return {"page_index": 0, "signature_rect": signature_rect(), "signature_labels": [PATIENT_SIGNATURE]}


_BOTOX_FORM = ("הסכמה מדעת להזרקת בוטוקס", "informed consent to botulinum toxin injection")
_BOTOX_TREATMENT = ("פרטי הטיפול", "treatment details")
_CT_FORM = ("הסכמה לצילום CT", "consent to a CT scan")
_CT_SCAN = ("פרטי הצילום", "scan details")
_PLAN_FORM = ("הסכמה לתוכנית טיפול והצעת מחיר", "consent to a treatment plan and quote")
_PLAN = ("תוכנית הטיפול", "treatment plan")
_QUESTIONNAIRE_FORM = ("שאלון רפואי", "medical questionnaire")
_HEALTH = ("פרטים רפואיים", "medical details")


def dental_processes(seed_type) -> tuple:
    """The four dental processes as catalog seeds. `seed_type` is processes.ProcessSeed."""
    return (
        seed_type(
            key=TREATMENT_PLAN,
            name="Dental treatment plan consent",
            description="Treatment plan and price quote the patient approves and signs before treatment starts.",
            template_filename="dental-treatment-plan-v1.pdf",
            layout=_layout(),
            required_documents=[_id_card()],
            optional_documents=[],
            required_fields=[
                *_patient_slots(_PLAN_FORM),
                _slot("treatment_plan", "Treatment plan", "תוכנית הטיפול", "text", True, _PLAN_FORM, _PLAN,
                      "הטיפולים המתוכננים, כפי שהרופא הציג אותם למטופל.", "The planned treatments as the dentist presented them."),
                _slot("total_price", "Total price", "מחיר כולל", "text", False, _PLAN_FORM, _PLAN,
                      "המחיר שהמטופל מאשר לתוכנית כולה.", "The price the patient approves for the whole plan."),
                _slot("payment_terms", "Payment terms", "תנאי תשלום", "text", True, _PLAN_FORM, _PLAN,
                      "איך ומתי ישולם המחיר.", "How and when the price is paid."),
                _slot("treating_doctor", "Treating dentist", "הרופא המטפל", "text", True, _PLAN_FORM, _PLAN,
                      "הרופא שהציג את התוכנית ויבצע אותה.", "The dentist who presented and will carry out the plan."),
                _slot("plan_date", "Plan date", "תאריך התוכנית", "date", False, _PLAN_FORM, _PLAN,
                      "היום שבו הוצגה התוכנית למטופל.", "The day the plan was presented to the patient."),
            ],
        ),
        seed_type(
            key=QUESTIONNAIRE,
            name="Dental medical questionnaire",
            description="The patient's medical history before treatment: medications, allergies, and background conditions.",
            template_filename="dental-medical-questionnaire-v1.pdf",
            layout=_layout(),
            required_documents=[_id_card()],
            optional_documents=[],
            required_fields=[
                *_patient_slots(_QUESTIONNAIRE_FORM),
                _slot("birth_date", "Date of birth", "תאריך לידה", "date", False, _QUESTIONNAIRE_FORM, _HEALTH,
                      "הגיל משפיע על בחירת הטיפול והמינון.", "Age bears on the choice of treatment and dose."),
                _slot("medications", "Regular medications", "תרופות קבועות", "text", True, _QUESTIONNAIRE_FORM, _HEALTH,
                      "תרופות שהמטופל נוטל, או \"אין\".", "Medications the patient takes, or \"none\"."),
                _slot("allergies", "Allergies", "אלרגיות", "text", True, _QUESTIONNAIRE_FORM, _HEALTH,
                      "רגישות לתרופות, לחומרים או למזון, או \"אין\".", "Sensitivity to drugs, materials, or food, or \"none\"."),
                _slot("chronic_conditions", "Background conditions", "מחלות רקע", "text", True, _QUESTIONNAIRE_FORM, _HEALTH,
                      "מחלות רקע וטיפולים קודמים רלוונטיים, או \"אין\".", "Background conditions and relevant past treatment, or \"none\"."),
                _slot("pregnancy", "Pregnancy or nursing", "הריון או הנקה", "text", True, _QUESTIONNAIRE_FORM, _HEALTH,
                      "הריון או הנקה משנים את הטיפולים והצילומים המותרים.", "Pregnancy or nursing changes which treatments and scans are allowed.",
                      required=False),
            ],
        ),
        seed_type(
            key=BOTOX,
            name="Botulinum toxin injection consent",
            description="Informed consent to a botulinum toxin (Botox) injection, with the treatment details the clinic fills in.",
            template_filename="dental-botox-consent-v1.pdf",
            layout=_layout(),
            required_documents=[_id_card()],
            optional_documents=[],
            required_fields=[
                *_patient_slots(_BOTOX_FORM),
                _slot("treatment_area", "Treatment area", "אזור הטיפול", "text", True, _BOTOX_FORM, _BOTOX_TREATMENT,
                      "האזור שבו יוזרק התכשיר.", "Where the product is injected."),
                _slot("product_name", "Product", "שם התכשיר", "text", False, _BOTOX_FORM, _BOTOX_TREATMENT,
                      "התכשיר שיוזרק.", "The product to be injected."),
                _slot("units", "Units", "מספר יחידות", "text", False, _BOTOX_FORM, _BOTOX_TREATMENT,
                      "המינון המתוכנן.", "The planned dose."),
                _slot("treating_doctor", "Treating dentist", "הרופא המטפל", "text", True, _BOTOX_FORM, _BOTOX_TREATMENT,
                      "הרופא שהסביר את הטיפול ויבצע אותו.", "The dentist who explained and will carry out the treatment."),
                _slot("treatment_date", "Treatment date", "תאריך הטיפול", "date", False, _BOTOX_FORM, _BOTOX_TREATMENT,
                      "היום שבו יבוצע הטיפול.", "The day of the treatment."),
            ],
        ),
        seed_type(
            key=CT,
            name="Dental CT scan consent",
            description="Consent to a dental CT (CBCT) scan, with the scan area and the referring dentist.",
            template_filename="dental-ct-consent-v1.pdf",
            layout=_layout(),
            required_documents=[_id_card()],
            optional_documents=[
                {
                    "type_key": "referral",
                    "label": "Referral",
                    "label_he": "הפניה",
                    "description": "A dentist's referral for imaging, naming the area to scan.",
                    "min_count": 1,
                },
            ],
            required_fields=[
                *_patient_slots(_CT_FORM),
                _slot("scan_area", "Scan area", "אזור הצילום", "text", True, _CT_FORM, _CT_SCAN,
                      "האזור שיצולם.", "The area to be scanned."),
                _slot("referring_doctor", "Referring dentist", "הרופא המפנה", "text", True, _CT_FORM, _CT_SCAN,
                      "הרופא שהפנה לצילום.", "The dentist who referred the patient for the scan."),
                _slot("scan_date", "Scan date", "תאריך הצילום", "date", False, _CT_FORM, _CT_SCAN,
                      "היום שבו יבוצע הצילום.", "The day of the scan."),
            ],
        ),
    )
