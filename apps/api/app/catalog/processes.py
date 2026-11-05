from dataclasses import dataclass

from pydantic import TypeAdapter

from app.domain.geometry import signature_rect
from app.schemas.process import DocumentTypeSpec, FieldSpec


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
            },
            {
                "type_key": "tax_form",
                "label": "Tax withholding form",
                "label_he": "טופס 101",
                "description": "Employee tax withholding form, including Israeli Form 101.",
                "min_count": 1,
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
            },
            {
                "key": "national_id",
                "label": "National ID",
                "label_he": "מספר זהות",
                "field_type": "id_number",
                "pdf_field_name": "national_id",
                "required": True,
                "rtl": False,
            },
            {
                "key": "email",
                "label": "Email",
                "label_he": "דוא״ל",
                "field_type": "email",
                "pdf_field_name": "email",
                "required": True,
                "rtl": False,
            },
            {
                "key": "phone",
                "label": "Mobile phone",
                "label_he": "טלפון נייד",
                "field_type": "phone",
                "pdf_field_name": "phone",
                "required": True,
                "rtl": False,
            },
            {
                "key": "address_he",
                "label": "Home address",
                "label_he": "כתובת",
                "field_type": "text",
                "pdf_field_name": "address_he",
                "required": True,
                "rtl": True,
            },
            {
                "key": "start_date",
                "label": "Start date",
                "label_he": "תאריך תחילת עבודה",
                "field_type": "date",
                "pdf_field_name": "start_date",
                "required": True,
                "rtl": False,
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
            },
            {
                "type_key": "id_copy",
                "label": "Buyer identification",
                "label_he": "תעודת זהות של הרוכש",
                "description": "Identity document of a party to the transaction.",
                "min_count": 1,
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
            },
            {
                "key": "seller_name",
                "label": "Seller name",
                "label_he": "שם המוכר",
                "field_type": "text",
                "pdf_field_name": "seller_name",
                "required": True,
                "rtl": False,
            },
            {
                "key": "property_address_he",
                "label": "Property address",
                "label_he": "כתובת הנכס",
                "field_type": "text",
                "pdf_field_name": "property_address_he",
                "required": True,
                "rtl": True,
            },
            {
                "key": "parcel_number",
                "label": "Parcel number",
                "label_he": "גוש וחלקה",
                "field_type": "text",
                "pdf_field_name": "parcel_number",
                "required": True,
                "rtl": False,
            },
            {
                "key": "price",
                "label": "Price",
                "label_he": "מחיר",
                "field_type": "text",
                "pdf_field_name": "price",
                "required": True,
                "rtl": False,
            },
            {
                "key": "contract_date",
                "label": "Contract date",
                "label_he": "תאריך חוזה",
                "field_type": "date",
                "pdf_field_name": "contract_date",
                "required": True,
                "rtl": False,
            },
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
