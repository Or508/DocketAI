import hashlib
import json
import secrets
from datetime import datetime, timezone

from app.domain.enums import CaseStatus
from app.models.case import Case
from app.models.signing_link import SigningLink

LinkState = str


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def link_state(link: SigningLink, case: Case, now: datetime) -> LinkState:
    current = as_utc(now)
    expires_at = as_utc(link.expires_at)
    assert current is not None and expires_at is not None
    revoked = link.revoked_at is not None
    if not revoked and link.completed_at is None and current < expires_at:
        return "open"
    download_expires_at = as_utc(link.download_expires_at)
    if (
        link.completed_at is not None
        and not revoked
        and download_expires_at is not None
        and current < download_expires_at
        and case.status == CaseStatus.SIGNED
        and link.signed_file_sha256 is not None
        and link.signed_file_sha256 == case.file_sha256
    ):
        return "completed"
    return "unavailable"


def review_digest(field_values: dict[str, str], template_filename: str) -> str:
    payload = json.dumps(field_values, sort_keys=True, ensure_ascii=False) + template_filename
    return hashlib.sha256(payload.encode()).hexdigest()
