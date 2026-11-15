from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SealVerification(BaseModel):
    """What anyone holding a verification code may learn about a signature.

    Nothing that identifies the signer beyond a masked name: no ID number,
    phone, address, bank account, case id or office.
    """

    valid: bool
    status: Literal["valid", "superseded"]
    verification_id: str
    process_type: str
    masked_client_name: str
    signed_at: datetime
    signed_pdf_sha256: str
    hash_matches: bool | None = None
