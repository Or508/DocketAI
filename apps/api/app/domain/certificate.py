import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

_ISRAEL = ZoneInfo("Asia/Jerusalem")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

PORTAL_CONSENT_TEXT = "I have reviewed this form and I am signing it electronically."
OFFICE_CONSENT_TEXT = "I confirm the signer reviewed this form and signed it in my presence."


@dataclass(frozen=True)
class SignerContext:
    channel: Literal["portal", "office"]
    ip: str | None
    user_agent: str | None


def clean_ip(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def clean_user_agent(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _CONTROL.sub("", value).strip()[:256]
    return cleaned or None


@dataclass(frozen=True)
class CertificateData:
    document_title: str
    case_reference: str
    client_name: str | None
    signer_verification_id: str
    channel: Literal["portal", "office"]
    ip: str | None
    user_agent: str | None
    consent_text: str
    created_at: datetime
    data_completed_at: datetime | None
    link_issued_at: datetime | None
    signed_at: datetime


def format_times(value: datetime) -> tuple[str, str]:
    moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    utc = moment.astimezone(timezone.utc)
    local = moment.astimezone(_ISRAEL)
    return utc.strftime("%Y-%m-%d %H:%M:%S %Z"), local.strftime("%Y-%m-%d %H:%M:%S %Z")
