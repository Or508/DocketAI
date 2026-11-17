"""The client's own document intake: a link the office sends, and what that link may see and do.

The link shows which documents the case needs and takes uploads into those drawers.
It never returns a value read from a document or typed by the office.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta

from fastapi import UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.exceptions import BadRequestError, ConflictError, GoneError, NotFoundError
from app.core.time import utcnow
from app.domain.case_scope import CaseScope
from app.domain.enums import AuditAction, CaseStatus, ClassificationSource, DocumentStatus
from app.domain.signing_links import as_utc, generate_token, hash_token
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.intake_link import IntakeLink
from app.schemas.intake import (
    IntakeDrawer,
    IntakeLinkCreated,
    IntakeRoutedFile,
    IntakeStatus,
    IntakeUploadResult,
)
from app.schemas.workspace import RoutedFile
from app.services.case_service import CaseService, _document_specs
from app.services.template_catalog import _TEXT_HE

logger = logging.getLogger(__name__)

CLIENT_ACTOR = "לקוח (העלאה עצמית)"
MAX_CLIENT_FILES = 5
_GONE = "This link is no longer active."
_TOKEN = re.compile(r"[A-Za-z0-9_-]{20,128}")
# How a client knows these documents, where that differs from the office's drawer label.
_CLIENT_LABELS = {
    "id_copy": "תעודת זהות",
    "proof_of_address": "אישור כתובת / ארנונה",
    "bank_confirmation": "אישור ניהול חשבון בנק",
}
_REASONS_HE = {
    "pending": "לא הצלחנו לזהות את סוג המסמך. הקובץ נשמר, והמשרד יתייק אותו.",
    "rejected": "לא ניתן היה לקבל את הקובץ. נסו קובץ PDF או תמונה ברורה.",
}


class IntakeService:
    def __init__(self, session: AsyncSession, container: Container, scope: CaseScope) -> None:
        self.session = session
        self.container = container
        self.scope = scope
        self.cases = CaseService(session, container, scope)

    async def create_link(self, case_id: uuid.UUID) -> IntakeLinkCreated:
        """Open a new intake link for an unsigned case. The link the case had before stops working."""
        case = await self.cases._get_case(case_id)
        if case.status == CaseStatus.SIGNED:
            raise ConflictError("This case is already signed.")
        now = utcnow()
        await self.session.execute(
            update(IntakeLink)
            .where(IntakeLink.case_id == case.id, IntakeLink.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        token = generate_token()
        hours = self.container.settings.intake_link_ttl_hours
        expires_at = now + timedelta(hours=hours) if hours else None
        link = IntakeLink(case_id=case.id, token_hash=hash_token(token), created_at=now, expires_at=expires_at)
        self.session.add(link)
        await self.session.flush()
        self.session.add(
            AuditLog(
                case_id=case.id,
                action=AuditAction.INTAKE_LINK_CREATED,
                actor=self.scope.actor,
                new_value={"link_id": str(link.id), "expires_at": expires_at.isoformat() if expires_at else None},
            )
        )
        await self.session.commit()
        logger.info("Intake link created for case %s", case.id)
        return IntakeLinkCreated(case_id=case.id, token=token, url_path=f"/upload/{token}", expires_at=expires_at)

    async def resolve(self, token: str) -> tuple[IntakeLink, Case]:
        """The link and its case. Unknown token: not found. Replaced, expired or signed: gone."""
        if not _TOKEN.fullmatch(token):
            raise NotFoundError(_GONE)
        link = await self.session.scalar(select(IntakeLink).where(IntakeLink.token_hash == hash_token(token)))
        if link is None:
            raise NotFoundError(_GONE)
        case = await self.cases._get_case(link.case_id)
        expires_at = as_utc(link.expires_at)
        expired = expires_at is not None and (as_utc(utcnow()) or expires_at) >= expires_at
        if link.revoked_at is not None or expired or case.status == CaseStatus.SIGNED:
            raise GoneError(_GONE)
        return link, case

    async def status(self, token: str) -> IntakeStatus:
        _link, case = await self.resolve(token)
        return IntakeStatus(**_public_status(case))

    async def upload(self, token: str, files: list[UploadFile], document_type: str | None) -> IntakeUploadResult:
        """File what the client sent. Each file goes to the drawer its name and text point to."""
        link, case = await self.resolve(token)
        if not files:
            raise BadRequestError("Choose at least one file.")
        chosen = (document_type or "").strip() or None
        if chosen is not None and len(files) != 1:
            raise BadRequestError("Name a document type for one file at a time.")
        # The upload ends the session's view of the case, so its id is taken first.
        case_id = case.id
        result = await self.cases.smart_upload(
            case_id,
            files,
            limit=MAX_CLIENT_FILES,
            from_client=True,
            document_type=chosen,
            audit_action=AuditAction.CLIENT_INTAKE_UPLOADED,
            audit_actor=CLIENT_ACTOR,
            audit_extra={"link_id": str(link.id)},
        )
        self.session.expire_all()
        case = await self.cases._get_case(case_id)
        return IntakeUploadResult(
            **_public_status(case),
            routed_files=[_public_file(item) for item in result.routed_files],
        )


def _label(spec) -> str:
    return _CLIENT_LABELS.get(spec.type_key) or spec.label_he or spec.label


def _public_status(case: Case) -> dict:
    required, _optional = _document_specs(case.process_definition)
    drawers: list[IntakeDrawer] = []
    for spec in required:
        held = [
            document
            for document in sorted(case.documents, key=lambda item: (item.created_at, str(item.id)), reverse=True)
            if document.role == "evidence"
            and document.document_type == spec.type_key
            and document.status != DocumentStatus.FAILED
            and (
                document.status == DocumentStatus.CLASSIFIED
                or document.classification_source == ClassificationSource.HUMAN
            )
        ]
        drawers.append(
            IntakeDrawer(
                document_type=spec.type_key,
                label_he=_label(spec),
                filled=len(held) >= max(1, spec.min_count),
                filename=held[0].original_filename if held else None,
            )
        )
    return {
        "case_id": case.id,
        "client_name": case.client_name or "",
        "process_type": case.process_definition.key,
        "process_title_he": _TEXT_HE.get(case.process_definition.key, (case.process_definition.name, ""))[0],
        "status": case.status.value,
        "required_drawers": drawers,
        "all_drawers_filled": bool(drawers) and all(item.filled for item in drawers),
    }


def _public_file(item: RoutedFile) -> IntakeRoutedFile:
    outcome = {"routed": "received", "unrouted": "pending", "rejected": "rejected"}[item.outcome]
    label = _CLIENT_LABELS.get(item.document_type or "") or item.drawer_label_he
    return IntakeRoutedFile(
        filename=item.filename,
        outcome=outcome,  # type: ignore[arg-type]
        document_type=item.document_type if outcome == "received" else None,
        label_he=label if outcome == "received" else None,
        reason_he=_REASONS_HE.get(outcome),
    )
