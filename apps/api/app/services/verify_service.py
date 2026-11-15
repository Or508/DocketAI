import hmac
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.core.time import utcnow
from app.domain.enums import AuditAction, CaseStatus
from app.domain.signing_links import as_utc
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.schemas.verify import SealVerification

_CODE = re.compile(r"DV-[0-9A-F]{12}")
_NOT_FOUND = "No signature is recorded under this verification code."


def normalize_code(raw: str) -> str | None:
    code = (raw or "").strip().upper()
    return code if _CODE.fullmatch(code) else None


def mask_name(name: str | None) -> str:
    """First name and the initial of the last: "אור יוסף" -> "אור י."."""
    parts = (name or "").split()
    if not parts:
        return ""
    if len(parts) == 1:
        return f"{parts[0][0]}."
    return f"{parts[0]} {parts[-1][0]}."


async def verify_seal(session: AsyncSession, raw_code: str, sha256: str | None) -> SealVerification:
    code = normalize_code(raw_code)
    if code is None:
        raise NotFoundError(_NOT_FOUND)
    # The signing audit row outlives a reopen, which clears the seal from the case itself.
    record = await session.scalar(
        select(AuditLog)
        .where(
            AuditLog.action == AuditAction.FILL_AND_SIGN,
            AuditLog.new_value["signer_verification_id"].as_string() == code,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    return await _describe(session, record, sha256)


async def verify_file(session: AsyncSession, sha256: str) -> SealVerification:
    """Find the seal a signed PDF belongs to from the file's own hash."""
    digest = sha256.strip().lower()
    record = await session.scalar(
        select(AuditLog)
        .where(
            AuditLog.action == AuditAction.FILL_AND_SIGN,
            AuditLog.new_value["file_sha256"].as_string() == digest,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    )
    return await _describe(session, record, digest)


async def _describe(session: AsyncSession, record: AuditLog | None, sha256: str | None) -> SealVerification:
    recorded = (record.new_value or {}) if record is not None else {}
    digest = str(recorded.get("file_sha256") or "").lower()
    code = normalize_code(str(recorded.get("signer_verification_id") or ""))
    if record is None or not digest or code is None:
        raise NotFoundError(_NOT_FOUND)
    case = await session.scalar(
        select(Case).where(Case.id == record.case_id).options(selectinload(Case.process_definition))
    )
    if case is None:
        raise NotFoundError(_NOT_FOUND)
    current = (
        case.status == CaseStatus.SIGNED
        and bool(case.output_path)
        and (case.signer_verification_id or "").upper() == code
        and (case.file_sha256 or "").lower() == digest
    )
    signed_at = (as_utc(case.signed_at) if current else None) or as_utc(record.created_at) or utcnow()
    matches = None
    if sha256 is not None:
        matches = hmac.compare_digest(sha256.strip().lower(), digest)
    return SealVerification(
        valid=current,
        status="valid" if current else "superseded",
        verification_id=code,
        process_type=case.process_definition.key,
        masked_client_name=mask_name(case.client_name),
        signed_at=signed_at,
        signed_pdf_sha256=digest,
        hash_matches=matches,
    )
