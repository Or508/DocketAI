from dataclasses import dataclass

from pydantic import TypeAdapter

from app.domain.geometry import signature_rect
from app.schemas.process import DocumentTypeSpec, FieldSpec


def _reading(*, one_person: bool, rules: list[dict], enabled: bool = False) -> dict:
    """Declared and off unless a process switches it on for its own documents."""
    return {"enabled": enabled, "one_person": one_person, "rules": rules}


def _provenance(
    form_he: str,
    form_en: str,
    section_he: str,
    section_en: str,
    purpose_he: str,
    purpose_en: str,
) -> dict[str, str]:
    return {
        "form_he": form_he,
        "section_he": section_he,
        "purpose_he": purpose_he,
        "form_en": form_en,
        "section_en": section_en,
        "purpose_en": purpose_en,
    }


def _bl_slot(
    key: str,
    label: str,
    label_he: str,
    field_type: str,
    rtl: bool,
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
        "provenance": _provenance(
            "טופס הצהרת מבוטח",
            "insured details form",
            "פרטים אישיים",
            "personal details",
            purpose_he,
            purpose_en,
        ),
    }


@dataclass(frozen=True)
class ProcessSeed:
    key: str
    name: str
    description: str
    required_documents: list[dict]
    optional_documents: list[dict]
    required_fields: list[dict]
    template_filename: str
    layout: dict


PROCESSES: tuple[ProcessSeed, ...] = (
    ProcessSeed(
        key="onboarding",
        name="Employee onboarding",
        description="Identity, tax, and bank documents for a new hire, then the onboarding form.",
        template_filename="onboarding-v1.pdf",
        layout={"page_index": 0, "signature_rect": signature_rect()},
        required_documents=[
            {
                "type_key": "id_copy",
                "label": "Government ID",
                "label_he": "צילום תעודת זהות",
                "description": "Government-issued identity card or passport bio page with a photo, full name, and ID number.",
                "min_count": 1,
                "reading": _reading(
                    one_person=True,
                    rules=[
                        {
                            "kind": "composite",
                            "slot_key": "full_name",
                            "parts": [
                                {"labels": ["שם פרטי", "first name"]},
                                {"labels": ["שם משפחה", "last name", "family name"]},
                            ],
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "full_name",
                            "labels": ["שם מלא", "full name", "full legal name"],
                        },
                        {"kind": "unique", "slot_key": "national_id"},
                    ],
                ),
            },
            {
                "type_key": "tax_form",
                "label": "Tax withholding form",
                "label_he": "טופס 101",
                "description": "Employee tax withholding form, including Israeli Form 101.",
                "min_count": 1,
                "reading": _reading(
                    one_person=False,
                    rules=[
                        {
                            "kind": "labeled",
                            "slot_key": "national_id",
                            "labels": ["מספר זהות", "תעודת זהות", "national id"],
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "start_date",
                            "labels": ["תאריך תחילת עבודה", "start date"],
                        },
                    ],
                ),
            },
            {
                "type_key": "bank_confirmation",
                "label": "Bank account confirmation",
                "label_he": "אישור ניהול חשבון",
                "description": "Bank letter confirming account ownership, an IBAN, or a voided check.",
                "min_count": 1,
            },
        ],
        optional_documents=[
            {
                "type_key": "proof_of_address",
                "label": "Proof of address",
                "label_he": "אישור כתובת",
                "description": "Utility bill, municipal tax notice, or official letter showing the resident's address.",
                "min_count": 1,
                "reading": _reading(
                    one_person=False,
                    rules=[
                        {
                            "kind": "labeled",
                            "slot_key": "address_he",
                            "labels": ["כתובת הנכס", "כתובת", "כתובת מגורים", "address"],
                        },
                    ],
                ),
            },
            {
                "type_key": "pension_form",
                "label": "Pension enrollment",
                "label_he": "טופס פנסיה",
                "description": "Pension or provident-fund enrollment form.",
                "min_count": 1,
            },
        ],
        required_fields=[
            {
                "key": "full_name",
                "label": "Full legal name",
                "label_he": "שם מלא",
                "field_type": "text",
                "pdf_field_name": "full_name",
                "required": True,
                "rtl": False,
                "provenance": _provenance(
                    "טופס קליטת עובד",
                    "employee onboarding form",
                    "פרטי העובד",
                    "employee details",
                    "השם המלא מזהה את האדם בטופס.",
                    "The full name identifies the person on the form.",
                ),
            },
            {
                "key": "national_id",
                "label": "National ID",
                "label_he": "מספר זהות",
                "field_type": "id_number",
                "pdf_field_name": "national_id",
                "required": True,
                "rtl": False,
                "provenance": _provenance(
                    "טופס קליטת עובד",
                    "employee onboarding form",
                    "פרטי העובד",
                    "employee details",
                    "מספר הזהות מזהה את האדם בטופס.",
                    "The ID number identifies the person on the form.",
                ),
            },
            {
                "key": "email",
                "label": "Email",
                "label_he": "דוא״ל",
                "field_type": "email",
                "pdf_field_name": "email",
                "required": True,
                "rtl": False,
                "provenance": _provenance(
                    "טופס קליטת עובד",
                    "employee onboarding form",
                    "פרטי קשר",
                    "contact details",
                    "כתובת הדוא״ל משמשת ליצירת קשר.",
                    "The email address is used for contact.",
                ),
            },
            {
                "key": "phone",
                "label": "Mobile phone",
                "label_he": "טלפון נייד",
                "field_type": "phone",
                "pdf_field_name": "phone",
                "required": True,
                "rtl": False,
                "provenance": _provenance(
                    "טופס קליטת עובד",
                    "employee onboarding form",
                    "פרטי קשר",
                    "contact details",
                    "מספר הטלפון משמש ליצירת קשר.",
                    "The phone number is used for contact.",
                ),
            },
            {
                "key": "address_he",
                "label": "Home address",
                "label_he": "כתובת",
                "field_type": "text",
                "pdf_field_name": "address_he",
                "required": True,
                "rtl": True,
                "provenance": _provenance(
                    "טופס קליטת עובד",
                    "employee onboarding form",
                    "כתובת מגורים",
                    "home address",
                    "הכתובת מציינת את מקום המגורים.",
                    "The address states the place of residence.",
                ),
            },
            {
                "key": "start_date",
                "label": "Start date",
                "label_he": "תאריך תחילת עבודה",
                "field_type": "date",
                "pdf_field_name": "start_date",
                "required": True,
                "rtl": False,
                "provenance": _provenance(
                    "טופס קליטת עובד",
                    "employee onboarding form",
                    "פרטי העסקה",
                    "employment details",
                    "התאריך מציין את יום תחילת העבודה.",
                    "The date states the first day of work.",
                ),
            },
        ],
    ),
    ProcessSeed(
        key="real_estate",
        name="Real estate closing",
        description="Purchase file: contract, land registry extract, identification, and tax clearance.",
        template_filename="real-estate-v1.pdf",
        layout={"page_index": 0, "signature_rect": signature_rect()},
        required_documents=[
            {
                "type_key": "purchase_agreement",
                "label": "Purchase agreement",
                "label_he": "הסכם מכר",
                "description": "Contract for the sale of real property between a buyer and a seller.",
                "min_count": 1,
            },
            {
                "type_key": "title_deed",
                "label": "Land registry extract",
                "label_he": "נסח טאבו",
                "description": "Land registry extract describing current ownership and the parcel.",
                "min_count": 1,
                "reading": _reading(
                    one_person=False,
                    rules=[
                        {
                            "kind": "labeled",
                            "slot_key": "property_address_he",
                            "labels": ["כתובת הנכס", "כתובת", "property address"],
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "parcel_number",
                            "labels": ["גוש וחלקה", "גוש/חלקה", "parcel"],
                        },
                    ],
                ),
            },
            {
                "type_key": "id_copy",
                "label": "Buyer identification",
                "label_he": "תעודת זהות של הרוכש",
                "description": "Identity document of a party to the transaction.",
                "min_count": 1,
                "reading": _reading(
                    one_person=True,
                    rules=[
                        {
                            "kind": "composite",
                            "slot_key": "buyer_name",
                            "parts": [
                                {"labels": ["שם פרטי", "first name"]},
                                {"labels": ["שם משפחה", "last name", "family name"]},
                            ],
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "buyer_name",
                            "labels": ["שם הרוכש", "שם מלא", "full name"],
                        },
                    ],
                ),
            },
            {
                "type_key": "tax_clearance",
                "label": "Tax clearance",
                "label_he": "אישור מס",
                "description": "Tax authority clearance or property-tax confirmation for the transaction.",
                "min_count": 1,
            },
        ],
        optional_documents=[
            {
                "type_key": "appraisal",
                "label": "Appraisal",
                "label_he": "שמאות",
                "description": "Property valuation or appraisal report.",
                "min_count": 1,
            },
            {
                "type_key": "mortgage_approval",
                "label": "Mortgage approval",
                "label_he": "אישור משכנתה",
                "description": "Lender approval or mortgage pre-approval letter.",
                "min_count": 1,
            },
        ],
        required_fields=[
            {
                "key": "buyer_name",
                "label": "Buyer name",
                "label_he": "שם הרוכש",
                "field_type": "text",
                "pdf_field_name": "buyer_name",
                "required": True,
                "rtl": False,
                "provenance": _provenance(
                    "טופס עסקת מקרקעין",
                    "real estate closing form",
                    "פרטי הצדדים",
                    "party details",
                    "השם מזהה את הרוכש בטופס.",
                    "The name identifies the buyer on the form.",
                ),
            },
            {
                "key": "seller_name",
                "label": "Seller name",
                "label_he": "שם המוכר",
                "field_type": "text",
                "pdf_field_name": "seller_name",
                "required": True,
                "rtl": False,
                "provenance": _provenance(
                    "טופס עסקת מקרקעין",
                    "real estate closing form",
                    "פרטי הצדדים",
                    "party details",
                    "השם מזהה את המוכר בטופס.",
                    "The name identifies the seller on the form.",
                ),
            },
            {
                "key": "property_address_he",
                "label": "Property address",
                "label_he": "כתובת הנכס",
                "field_type": "text",
                "pdf_field_name": "property_address_he",
                "required": True,
                "rtl": True,
                "provenance": _provenance(
                    "טופס עסקת מקרקעין",
                    "real estate closing form",
                    "פרטי הנכס",
                    "property details",
                    "הכתובת מציינת את מיקום הנכס.",
                    "The address states where the property is.",
                ),
            },
            {
                "key": "parcel_number",
                "label": "Parcel number",
                "label_he": "גוש וחלקה",
                "field_type": "text",
                "pdf_field_name": "parcel_number",
                "required": True,
                "rtl": False,
                "provenance": _provenance(
                    "טופס עסקת מקרקעין",
                    "real estate closing form",
                    "פרטי הנכס",
                    "property details",
                    "המספר מזהה את החלקה בטופס.",
                    "The number identifies the parcel on the form.",
                ),
            },
            {
                "key": "price",
                "label": "Price",
                "label_he": "מחיר",
                "field_type": "text",
                "pdf_field_name": "price",
                "required": True,
                "rtl": False,
                "provenance": _provenance(
                    "טופס עסקת מקרקעין",
                    "real estate closing form",
                    "פרטי התמורה",
                    "price details",
                    "הסכום מציין את המחיר הרשום בטופס.",
                    "The amount states the price recorded on the form.",
                ),
            },
            {
                "key": "contract_date",
                "label": "Contract date",
                "label_he": "תאריך חוזה",
                "field_type": "date",
                "pdf_field_name": "contract_date",
                "required": True,
                "rtl": False,
                "provenance": _provenance(
                    "טופס עסקת מקרקעין",
                    "real estate closing form",
                    "פרטי התמורה",
                    "price details",
                    "התאריך מציין את יום החוזה הרשום בטופס.",
                    "The date states the contract day recorded on the form.",
                ),
            },
        ],
    ),
    ProcessSeed(
        key="bl_6101",
        name="Insured details declaration",
        description="Blank official form filled from the client's documents. The office reviews personal details, then the client signs the uploaded form.",
        template_filename="bl-6101-uploaded",
        layout={
            "sign_source": "uploaded_form",
            "signature_labels": ["חתימת המבוטח"],
            "flat_form": {
                "sections": [
                    "פרטי המבוטח",
                    "פרטי בן/בת הזוג",
                    "כתובת מגורים ופרטי התקשרות",
                    "מען למכתבים",
                    "פרטי חשבון הבנק של המבוטח",
                ],
                "slot_section": {
                    "national_id": "פרטי המבוטח",
                    "first_name": "פרטי המבוטח",
                    "last_name": "פרטי המבוטח",
                    "street": "כתובת מגורים ופרטי התקשרות",
                    "city": "כתובת מגורים ופרטי התקשרות",
                    "house_number": "כתובת מגורים ופרטי התקשרות",
                    "phone": "כתובת מגורים ופרטי התקשרות",
                    "bank_name": "פרטי חשבון הבנק של המבוטח",
                    "bank_branch": "פרטי חשבון הבנק של המבוטח",
                    "bank_account": "פרטי חשבון הבנק של המבוטח",
                },
            },
        },
        required_documents=[
            {
                "type_key": "id_copy",
                "label": "Government ID",
                "label_he": "צילום תעודת זהות",
                "description": "Government-issued identity card or passport bio page with a photo, given name, family name, and ID number.",
                "min_count": 1,
                "reading": _reading(
                    enabled=True,
                    one_person=True,
                    rules=[
                        {
                            "kind": "labeled",
                            "slot_key": "first_name",
                            "labels": ["שם פרטי", "השם הפרטי", "first name", "given name"],
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "last_name",
                            "labels": ["שם משפחה", "שם המשפחה", "last name", "family name", "surname"],
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "national_id",
                            "labels": ["מספר הזהות", "מספר זהות", "id number"],
                        },
                        {"kind": "unique", "slot_key": "national_id"},
                    ],
                ),
            },
            {
                "type_key": "proof_of_address",
                "label": "Proof of address",
                "label_he": "אישור כתובת",
                "description": "Utility bill or municipal tax notice showing the resident's address.",
                "min_count": 1,
                "reading": _reading(
                    enabled=True,
                    one_person=False,
                    rules=[
                        {
                            "kind": "labeled",
                            "slot_key": "street",
                            "labels": ["רחוב"],
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "city",
                            "labels": ["עיר", "ישוב", "יישוב"],
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "house_number",
                            "labels": ["מספר בית", "מס' בית"],
                        },
                        # A bill prints street, house number and town on one address line.
                        {
                            "kind": "labeled",
                            "slot_key": "street",
                            "labels": ["כתובת הנכס", "כתובת"],
                            "piece": "street",
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "house_number",
                            "labels": ["כתובת הנכס", "כתובת"],
                            "piece": "house_number",
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "city",
                            "labels": ["כתובת הנכס", "כתובת"],
                            "piece": "city",
                        },
                    ],
                ),
            },
            {
                "type_key": "bank_confirmation",
                "label": "Bank account confirmation",
                "label_he": "אישור ניהול חשבון",
                "description": "Bank letter confirming the account holder's bank, branch, and account number.",
                "min_count": 1,
                "reading": _reading(
                    enabled=True,
                    one_person=False,
                    rules=[
                        {
                            "kind": "labeled",
                            "slot_key": "bank_name",
                            "labels": ["שם הבנק", "בנק"],
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "bank_branch",
                            "labels": ["מספר סניף", "סניף"],
                        },
                        {
                            "kind": "labeled",
                            "slot_key": "bank_account",
                            "labels": ["מספר חשבון", "חשבון"],
                        },
                    ],
                ),
            },
        ],
        optional_documents=[],
        required_fields=[
            _bl_slot("national_id", "National ID", "מספר זהות", "id_number", False, "מספר הזהות מזהה את האדם בטופס.", "The ID number identifies the person on the form."),
            _bl_slot("first_name", "First name", "שם פרטי", "text", True, "השם הפרטי רושם את הפרט האישי בטופס.", "The first name records the personal detail on the form."),
            _bl_slot("last_name", "Last name", "שם משפחה", "text", True, "שם המשפחה רושם את הפרט האישי בטופס.", "The last name records the personal detail on the form."),
            _bl_slot("city", "City of residence", "יישוב", "text", True, "העיר רושמת את מקום המגורים בטופס.", "The city records the place of residence on the form."),
            _bl_slot("street", "Street", "רחוב / תא דואר", "text", True, "הרחוב רושם את מקום המגורים בטופס.", "The street records the place of residence on the form."),
            _bl_slot("house_number", "House number", "מס' בית", "text", False, "מספר הבית רושם את מקום המגורים בטופס.", "The house number records the place of residence on the form.", required=False),
            _bl_slot("phone", "Phone", "טלפון נייד", "phone", False, "מספר הטלפון משמש ליצירת קשר.", "The phone number is used for contact."),
            _bl_slot("bank_name", "Bank name", "שם הבנק", "text", True, "שם הבנק רושם את פרט החשבון בטופס.", "The bank name records the account detail on the form."),
            _bl_slot("bank_branch", "Branch number", "מס' סניף", "text", False, "מספר הסניף רושם את פרט החשבון בטופס.", "The branch number records the account detail on the form."),
            _bl_slot("bank_account", "Account number", "מספר החשבון", "text", False, "מספר החשבון רושם את פרט החשבון בטופס.", "The account number records the account detail on the form."),
        ],
    ),
)


def _validate_catalog() -> None:
    documents = TypeAdapter(list[DocumentTypeSpec])
    fields = TypeAdapter(list[FieldSpec])
    for process in PROCESSES:
        documents.validate_python(process.required_documents)
        documents.validate_python(process.optional_documents)
        parsed_fields = fields.validate_python(process.required_fields)
        keys = [item.key for item in parsed_fields]
        pdf_names = [item.pdf_field_name for item in parsed_fields]
        if len(keys) != len(set(keys)) or len(pdf_names) != len(set(pdf_names)):
            raise RuntimeError(f"Duplicate field keys in process {process.key}")
        type_keys = [item["type_key"] for item in process.required_documents]
        type_keys += [item["type_key"] for item in process.optional_documents]
        if len(type_keys) != len(set(type_keys)):
            raise RuntimeError(f"Duplicate document types in process {process.key}")


_validate_catalog()
