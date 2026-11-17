from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import CaseStatus


class ClientCase(BaseModel):
    case_id: UUID
    process_type: str
    status: CaseStatus
    created_at: datetime | None
    signed_at: datetime | None
    verification_id: str | None


class ClientRead(BaseModel):
    """One client of the office, gathered from every case that names them."""

    # "id:<number>" when a case holds the ID number, else "name:<normalized name>".
    client_key: str
    client_name: str
    id_number: str | None
    phone: str | None
    address_summary: str | None
    # Bank and branch in full; the account number shows its last four digits only.
    bank_summary: str | None
    total_cases: int
    signed_cases: int
    # How many of the three vault documents (ID, proof of address, bank letter) a new case can reuse.
    reusable_docs_count: int
    reusable_doc_types: list[str] = Field(default_factory=list)
    latest_case_id: UUID
    cases: list[ClientCase]


class QuickCaseRequest(BaseModel):
    source_case_id: UUID
    process_type: str = Field(min_length=1, max_length=64)

    model_config = ConfigDict(str_strip_whitespace=True)
