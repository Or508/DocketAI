import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.exceptions import ConflictError, GoneError, NotFoundError, RateLimitError
from app.core.time import utcnow
from app.domain.case_scope import CaseScope
from app.domain.certificate import PORTAL_CONSENT_TEXT, SignerContext
from app.domain.enums import AuditAction, CaseStatus
from app.domain.signing_links import as_utc, generate_token, hash_token, link_state, review_digest
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.signing_link import SigningLink
from app.schemas.chat import ChatMessageRead
from app.schemas.gap import FillAndSignRequest
from app.schemas.portal import (
    PortalProcess,
    PortalSeal,
    PortalSignRequest,
    PortalView,
    SigningLinkCreated,
    SigningLinkRead,
)
from app.services.case_service import CaseService, _field_specs
from app.services.chat_collector import ask
from app.services.field_validator import missing_required_fields

logger = logging.getLogger(__name__)

_NOT_READY = "This case is not ready for a signer."
_GONE = "This link is no longer active. Contact the office for a new one."


class PortalService:
    def __init__(self, session: AsyncSession, container: Container, scope: CaseScope) -> None:
        self.session = session
        self.container = container
        self.scope = scope
        self.cases = CaseService(session, container, scope)

    async def create_link(self, case_id: uuid.UUID) -> SigningLinkCreated:
        case = await self.cases._get_case(case_id)
        if case.status == CaseStatus.SIGNED:
            raise ConflictError("This case is already signed.")
        gap = self.cases._gap(case)
        blocked = bool(gap.missing or gap.unrecognized or gap.in_progress)
        if blocked or case.status in {CaseStatus.PROCESSING, CaseStatus.DRAFT, CaseStatus.FAILED}:
            raise ConflictError(_NOT_READY)
        now = utcnow()
        await self.session.execute(
            update(SigningLink)
            .where(
                SigningLink.case_id == case.id,
                SigningLink.revoked_at.is_(None),
                SigningLink.completed_at.is_(None),
            )
            .values(revoked_at=now, revoke_reason="replaced")
        )
        token = generate_token()
        expires_at = now + timedelta(hours=self.container.settings.signing_link_ttl_hours)
        link = SigningLink(
            case_id=case.id,
            token_hash=hash_token(token),
            created_at=now,
            expires_at=expires_at,
            chat_turns=0,
        )
        self.session.add(link)
        self.session.add(
            AuditLog(
                case_id=case.id,
                action=AuditAction.SIGNING_LINK_CREATED,
                actor=self.scope.actor,
                new_value={"expires_at": expires_at.isoformat()},
            )
        )
        await self.session.commit()
        logger.info("Signing link created for case %s", case.id)
        base = self.container.settings.public_web_url.rstrip("/")
        return SigningLinkCreated(url=f"{base}/sign/{token}", expires_at=expires_at)

    async def revoke_link(self, case_id: uuid.UUID) -> None:
        case = await self.cases._get_case(case_id)
        now = utcnow()
        result = await self.session.execute(
            update(SigningLink)
            .where(
                SigningLink.case_id == case.id,
                SigningLink.revoked_at.is_(None),
                SigningLink.completed_at.is_(None),
            )
            .values(revoked_at=now, revoke_reason="office")
        )
        if result.rowcount != 1:
            raise NotFoundError("There is no open signing link.")
        self.session.add(
            AuditLog(
                case_id=case.id,
                action=AuditAction.SIGNING_LINK_REVOKED,
                actor=self.scope.actor,
                new_value={"revoke_reason": "office"},
            )
        )
        await self.session.commit()

    async def current(self, case_id: uuid.UUID) -> SigningLinkRead:
        case = await self.cases._get_case(case_id)
        link = await self.session.scalar(
            select(SigningLink).where(SigningLink.case_id == case.id).order_by(SigningLink.created_at.desc())
        )
        if link is None:
            raise NotFoundError("There is no signing link.")
        state = link_state(link, case, utcnow())
        created_at = as_utc(link.created_at)
        expires_at = as_utc(link.expires_at)
        assert created_at is not None and expires_at is not None
        return SigningLinkRead(state=state, created_at=created_at, expires_at=expires_at)  # type: ignore[arg-type]

    async def resolve(self, token: str) -> tuple[SigningLink, Case]:
        link = await self.session.scalar(select(SigningLink).where(SigningLink.token_hash == hash_token(token)))
        if link is None:
            raise NotFoundError("This link is no longer active.")
        case = await self.cases._get_case(link.case_id)
        if link_state(link, case, utcnow()) == "unavailable":
            raise GoneError(_GONE)
        return link, case

    def view(self, link: SigningLink, case: Case) -> PortalView:
        state = link_state(link, case, utcnow())
        if state == "unavailable":
            raise GoneError(_GONE)
        fields = _field_specs(case.process_definition)
        values = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        missing = missing_required_fields(fields, values)
        blockers = self.cases._blockers(case, self.cases._gap(case), values)
        created = as_utc(link.created_at)
        messages: list[ChatMessageRead] = []
        for item in case.chat_history or []:
            stamp = _message_time(item.get("created_at"))
            if created is None or stamp is None or stamp < created:
                continue
            messages.append(ChatMessageRead.model_validate(item))
        if not messages and missing:
            messages.append(ChatMessageRead(role="assistant", content=ask(missing[0]), created_at=utcnow()))
        expires_at = as_utc(link.expires_at)
        assert expires_at is not None
        signed_at = as_utc(case.signed_at) if state == "completed" else None
        return PortalView(
            state=state,  # type: ignore[arg-type]
            process=PortalProcess(name=case.process_definition.name, required_fields=fields),
            client_name=case.client_name,
            messages=messages,
            field_values=values,
            missing_fields=missing,
            ready_to_sign=state == "open" and not blockers,
            waiting_on_office=any(not item.startswith("Still need:") for item in blockers),
            review_digest=review_digest(values, case.process_definition.template_filename),
            expires_at=expires_at,
            signed_at=signed_at,
            download_expires_at=as_utc(link.download_expires_at) if state == "completed" else None,
            consent_text=PORTAL_CONSENT_TEXT,
            seal=_seal(case, signed_at) if state == "completed" else None,
        )

    async def sign(
        self,
        link: SigningLink,
        case: Case,
        payload: PortalSignRequest,
        context: SignerContext,
    ) -> None:
        self.require_open(link, case)
        values = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        digest = review_digest(values, case.process_definition.template_filename)
        if digest != payload.review_digest:
            raise ConflictError("The form changed. Please review it again.")
        hours = self.container.settings.signing_link_download_hours

        async def before_fill() -> None:
            now = utcnow()
            result = await self.session.execute(
                update(SigningLink)
                .where(
                    SigningLink.id == link.id,
                    SigningLink.revoked_at.is_(None),
                    SigningLink.completed_at.is_(None),
                )
                .values(completed_at=now, download_expires_at=now + timedelta(hours=hours))
            )
            if result.rowcount != 1:
                raise ConflictError("This link was already used.")
            self.session.expire(link)
            await self.session.refresh(link)

        async def after_sign(artifact) -> dict[str, object]:
            link.signed_file_sha256 = artifact.file_sha256
            return {"link_id": str(link.id), "consent": True}

        await self.cases._sign_case(
            case,
            FillAndSignRequest(signature_png_base64=payload.signature_png_base64, consent=True),
            actor="signer",
            context=context,
            before_fill=before_fill,
            after_sign=after_sign,
            link_issued_at=as_utc(link.created_at),
        )

    async def consume_chat_turn(self, link: SigningLink) -> None:
        cap = self.container.settings.signing_link_max_chat_turns
        result = await self.session.execute(
            update(SigningLink)
            .where(SigningLink.id == link.id, SigningLink.chat_turns < cap)
            .values(chat_turns=SigningLink.chat_turns + 1)
        )
        if result.rowcount != 1:
            raise RateLimitError()
        self.session.expire(link)
        await self.session.commit()

    def require_open(self, link: SigningLink, case: Case) -> None:
        if link_state(link, case, utcnow()) != "open":
            raise ConflictError("This form is already signed.")

    async def preview_pdf(self, case: Case) -> bytes:
        fields = _field_specs(case.process_definition)
        values = {str(key): str(value) for key, value in (case.field_values or {}).items()}
        pdf_values: dict[str, str] = {}
        rtl_fields: set[str] = set()
        for spec in fields:
            value = values.get(spec.key, "").strip()
            if not value:
                continue
            pdf_values[spec.pdf_field_name] = value
            if spec.rtl or _hebrew(value):
                rtl_fields.add(spec.pdf_field_name)
        template = self.container.settings.resolved_template_dir / case.process_definition.template_filename
        if not template.is_file():
            raise ConflictError("The form template is missing.")
        return self.container.pdf_filler.render_preview(
            template_path=template,
            values=pdf_values,
            rtl_fields=rtl_fields,
        )


def _recorded_ip(case: Case) -> str | None:
    data = case.certificate_data
    if not isinstance(data, dict):
        return None
    ip = data.get("signer_ip")
    if not isinstance(ip, str) or not ip.strip():
        return None
    return ip


def _seal(case: Case, signed_at: datetime | None) -> PortalSeal:
    assert signed_at is not None
    assert case.signer_verification_id is not None
    assert case.file_sha256 is not None
    return PortalSeal(
        signed_at=signed_at,
        signer_verification_id=case.signer_verification_id,
        file_sha256=case.file_sha256,
        recorded_ip=_recorded_ip(case),
        time_zone="Asia/Jerusalem",
    )


def _hebrew(value: str) -> bool:
    from app.domain.text_layout import contains_hebrew

    return contains_hebrew(value)


def _message_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return as_utc(value)
    if isinstance(value, str):
        try:
            return as_utc(datetime.fromisoformat(value))
        except ValueError:
            return None
    return None
