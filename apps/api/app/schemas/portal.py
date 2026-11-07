from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.chat import ChatMessageRead
from app.schemas.process import FieldSpec


class SigningLinkRead(BaseModel):
    state: Literal["open", "completed", "unavailable"]
    created_at: datetime
    expires_at: datetime


class SigningLinkCreated(BaseModel):
    url: str
    expires_at: datetime


class PortalProcess(BaseModel):
    name: str
    required_fields: list[FieldSpec]


class PortalSeal(BaseModel):
    signed_at: datetime
    signer_verification_id: str
    file_sha256: str
    recorded_ip: str | None
    time_zone: Literal["Asia/Jerusalem"]


class PortalView(BaseModel):
    state: Literal["open", "completed"]
    process: PortalProcess
    client_name: str | None
    messages: list[ChatMessageRead]
    field_values: dict[str, str]
    missing_fields: list[FieldSpec]
    ready_to_sign: bool
    waiting_on_office: bool
    review_digest: str | None
    expires_at: datetime
    signed_at: datetime | None
    download_expires_at: datetime | None
    consent_text: str
    seal: PortalSeal | None = None


class PortalSignRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signature_png_base64: str = Field(min_length=20, max_length=3_000_000)
    review_digest: str
    consent: Literal[True]
