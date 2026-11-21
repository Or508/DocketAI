"""Messages to clients: send a fresh link by email or WhatsApp, and remind until the client acts.

Email goes out by itself. WhatsApp is a link the office opens on its own device and sends from its own
account, so a WhatsApp reminder waits in the office's list instead of going out by itself.
Reminders stop on their own when the client hands in every document, signs, or the link is replaced or closed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError, RateLimitError
from app.core.time import utcnow
from app.domain.case_scope import CaseScope, case_query
from app.domain.enums import AuditAction, CaseStatus
from app.domain.outreach import (
    allowed_now,
    clean_email,
    clean_phone,
    mask_email,
    mask_phone,
    next_allowed,
    reminder_at,
    show_phone,
    whatsapp_url,
    wording,
)
from app.domain.signing_links import as_utc, hash_token
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.intake_link import IntakeLink
from app.models.organization import Organization
from app.models.outreach import CaseOutreach, OutboundMessage
from app.services.demo_guard import is_demo, refuse_demo_email
from app.models.signing_link import SigningLink
from app.schemas.outreach import DueReminder, OutreachMessage, OutreachSendRequest, OutreachSent, OutreachState
from app.services.case_service import CaseService
from app.services.email_sender import EmailError, EmailSender, build_message
from app.services.intake_service import IntakeService
from app.services.portal_service import PortalService
from app.services.security_service import open_secret, seal_secret

logger = logging.getLogger(__name__)

_NO_CONTACT = {
    "email": "צריך כתובת אימייל תקינה.",
    "whatsapp": "צריך מספר נייד תקין, למשל 050-1234567.",
}


def _message_read(row: OutboundMessage) -> OutreachMessage:
    return OutreachMessage(
        id=row.id,
        purpose=row.purpose,  # type: ignore[arg-type]
        kind=row.kind,  # type: ignore[arg-type]
        channel=row.channel,  # type: ignore[arg-type]
        recipient=row.recipient,
        status=row.status,  # type: ignore[arg-type]
        error=row.error,
        created_at=row.created_at,
    )


class OutreachService:
    def __init__(self, session: AsyncSession, container: Container, scope: CaseScope) -> None:
        self.session = session
        self.container = container
        self.scope = scope
        self.settings = container.settings
        self.cases = CaseService(session, container, scope)
        self.email = EmailSender(self.settings)

    # ------------------------------------------------------------------------------------------
    # Office actions.
    # ------------------------------------------------------------------------------------------

    async def send(self, case_id: uuid.UUID, request: OutreachSendRequest) -> OutreachSent:
        case = await self.cases._get_case(case_id)
        if case.status == CaseStatus.SIGNED:
            raise ConflictError("התיק כבר חתום.")
        email = clean_email(request.email)
        phone = clean_phone(request.phone)
        if request.email and email is None:
            raise BadRequestError(_NO_CONTACT["email"])
        if request.phone and phone is None:
            raise BadRequestError(_NO_CONTACT["whatsapp"])
        if (request.channel == "email" and email is None) or (request.channel == "whatsapp" and phone is None):
            raise BadRequestError(_NO_CONTACT[request.channel])
        if request.channel == "email" and not self.email.available:
            raise ConflictError("שליחת אימייל לא הוגדרה בשרת. אפשר לשלוח בוואטסאפ או להעתיק את הקישור.")
        if request.channel == "email":
            refuse_demo_email(await self.session.get(Organization, case.organization_id))
        await self._check_daily_cap(case.id)

        # A new link replaces the open one, as it does from the office's own buttons.
        token, url, link_id, expires_at = await self._new_link(case, request.purpose)
        now = utcnow()
        outreach = await self.session.get(CaseOutreach, case.id)
        if outreach is None:
            outreach = CaseOutreach(case_id=case.id)
            self.session.add(outreach)
        outreach.email = email or outreach.email
        outreach.phone = phone or outreach.phone
        outreach.purpose = request.purpose
        outreach.channel = request.channel
        outreach.link_id = link_id
        outreach.token_sealed = seal_secret(self.settings, token)
        outreach.reminders_enabled = request.reminders
        outreach.first_sent_at = now
        outreach.reminders_sent = 0
        outreach.stopped_reason = None if request.reminders else "turned_off"
        outreach.next_reminder_at = self._schedule(now, 0) if request.reminders else None

        office = await self._office_name(case)
        message, wa = await self._deliver(case, outreach, "first", url, expires_at, office)
        await self.session.commit()
        return OutreachSent(
            message=_message_read(message), url=url, whatsapp_url=wa, next_reminder_at=outreach.next_reminder_at
        )

    async def state(self, case_id: uuid.UUID) -> OutreachState:
        case = await self.cases._get_case(case_id)
        outreach = await self.session.get(CaseOutreach, case.id)
        rows = await self.session.scalars(
            select(OutboundMessage)
            .where(OutboundMessage.case_id == case.id)
            .order_by(OutboundMessage.created_at.desc())
            .limit(50)
        )
        if outreach is not None and outreach.stopped_reason is None:
            await self._refresh_stop(case, outreach)
        return OutreachState(
            email=outreach.email if outreach else None,
            phone=outreach.phone if outreach else None,
            phone_display=show_phone(outreach.phone) if outreach and outreach.phone else None,
            purpose=outreach.purpose if outreach else None,  # type: ignore[arg-type]
            channel=outreach.channel if outreach else None,  # type: ignore[arg-type]
            reminders_enabled=bool(outreach and outreach.reminders_enabled),
            reminders_sent=outreach.reminders_sent if outreach else 0,
            next_reminder_at=outreach.next_reminder_at if outreach and outreach.stopped_reason is None else None,
            stopped_reason=outreach.stopped_reason if outreach else None,
            email_available=self.email.available,
            messages=[_message_read(row) for row in rows],
        )

    async def set_reminders(self, case_id: uuid.UUID, enabled: bool) -> OutreachState:
        case = await self.cases._get_case(case_id)
        outreach = await self.session.get(CaseOutreach, case.id)
        if outreach is None or outreach.first_sent_at is None:
            raise ConflictError("עדיין לא נשלחה הודעה ללקוח בתיק הזה.")
        outreach.reminders_enabled = enabled
        if enabled:
            outreach.stopped_reason = None
            outreach.next_reminder_at = self._schedule(as_utc(outreach.first_sent_at), outreach.reminders_sent) or (
                self._soonest(utcnow())
            )
        else:
            outreach.stopped_reason = "turned_off"
            outreach.next_reminder_at = None
        self.session.add(
            AuditLog(
                case_id=case.id,
                action=AuditAction.REMINDERS_CHANGED,
                actor=self.scope.actor,
                new_value={"enabled": enabled},
            )
        )
        await self.session.commit()
        return await self.state(case_id)

    async def remind_now(self, case_id: uuid.UUID) -> OutreachSent:
        """One reminder with the link already sent: by email, or as a WhatsApp link for the office to open."""
        case = await self.cases._get_case(case_id)
        outreach = await self.session.get(CaseOutreach, case.id)
        if outreach is None or outreach.token_sealed is None:
            raise ConflictError("עדיין לא נשלח ללקוח קישור מכאן.")
        reason = await self._stop_reason(case, outreach)
        if reason is not None:
            outreach.stopped_reason = reason
            outreach.next_reminder_at = None
            await self.session.commit()
            raise ConflictError(_STOPPED_MESSAGE.get(reason, "אין למה להזכיר: הקישור כבר לא פעיל."))
        if outreach.channel == "email" and not self.email.available:
            raise ConflictError("שליחת אימייל לא הוגדרה בשרת.")
        if outreach.channel == "email":
            refuse_demo_email(await self.session.get(Organization, case.organization_id))
        await self._check_daily_cap(case.id)
        url, expires_at = await self._current_link(outreach)
        office = await self._office_name(case)
        message, wa = await self._deliver(case, outreach, "reminder", url, expires_at, office)
        self._advance(outreach)
        await self.session.commit()
        return OutreachSent(
            message=_message_read(message), url=url, whatsapp_url=wa, next_reminder_at=outreach.next_reminder_at
        )

    async def due_whatsapp(self) -> list[DueReminder]:
        """WhatsApp reminders whose time has come, for this office to send by hand."""
        now = utcnow()
        stmt = (
            select(CaseOutreach, Case)
            .join(Case, Case.id == CaseOutreach.case_id)
            .where(
                CaseOutreach.channel == "whatsapp",
                CaseOutreach.reminders_enabled.is_(True),
                CaseOutreach.stopped_reason.is_(None),
                CaseOutreach.next_reminder_at.is_not(None),
                CaseOutreach.next_reminder_at <= now,
            )
            .order_by(CaseOutreach.next_reminder_at)
            .limit(100)
        )
        if self.scope.organization_id is not None:
            stmt = stmt.where(Case.organization_id == self.scope.organization_id)
        due: list[DueReminder] = []
        for outreach, case in (await self.session.execute(stmt)).all():
            if await self._refresh_stop(case, outreach):
                continue
            due.append(
                DueReminder(
                    case_id=case.id,
                    case_name=case.name,
                    client_name=case.client_name,
                    purpose=outreach.purpose,  # type: ignore[arg-type]
                    phone_display=show_phone(outreach.phone or ""),
                    due_at=as_utc(outreach.next_reminder_at),  # type: ignore[arg-type]
                )
            )
        await self.session.commit()
        return due

    # ------------------------------------------------------------------------------------------
    # The reminder loop (system scope).
    # ------------------------------------------------------------------------------------------

    async def send_due_emails(self, limit: int = 50) -> int:
        """Send every email reminder that is due. Safe to run from several processes at once."""
        now = utcnow()
        if not self.email.available:
            return 0
        if not allowed_now(now, start_hour=self.settings.reminder_start_hour, end_hour=self.settings.reminder_end_hour):
            return 0
        candidates = (
            await self.session.scalars(
                select(CaseOutreach)
                .where(
                    CaseOutreach.channel == "email",
                    CaseOutreach.reminders_enabled.is_(True),
                    CaseOutreach.stopped_reason.is_(None),
                    CaseOutreach.next_reminder_at.is_not(None),
                    CaseOutreach.next_reminder_at <= now,
                )
                .order_by(CaseOutreach.next_reminder_at)
                .limit(limit)
            )
        ).all()
        sent = 0
        for outreach in candidates:
            # Claim the row: only the process whose update matches the due time sends this reminder.
            claimed = await self.session.execute(
                update(CaseOutreach)
                .where(
                    CaseOutreach.case_id == outreach.case_id,
                    CaseOutreach.next_reminder_at == outreach.next_reminder_at,
                )
                .values(next_reminder_at=None)
                .execution_options(synchronize_session=False)
            )
            await self.session.commit()
            if claimed.rowcount != 1:
                continue
            await self.session.refresh(outreach)
            try:
                if await self._email_reminder(outreach):
                    sent += 1
            except Exception:
                logger.exception("Reminder for case %s failed", outreach.case_id)
                await self.session.rollback()
        return sent

    async def _email_reminder(self, outreach: CaseOutreach) -> bool:
        case = await self.session.scalar(case_query(self.scope).where(Case.id == outreach.case_id))
        if case is None:
            return False
        organization = await self.session.get(Organization, case.organization_id)
        if is_demo(organization):
            outreach.stopped_reason = "turned_off"
            outreach.next_reminder_at = None
            await self.session.commit()
            return False
        reason = await self._stop_reason(case, outreach)
        if reason is not None:
            outreach.stopped_reason = reason
            await self.session.commit()
            return False
        if await self._sent_today(case.id) >= self.settings.max_messages_per_case_per_day:
            outreach.next_reminder_at = utcnow() + timedelta(days=1)
            await self.session.commit()
            return False
        url, expires_at = await self._current_link(outreach)
        office = await self._office_name(case)
        await self._deliver(case, outreach, "reminder", url, expires_at, office)
        self._advance(outreach)
        await self.session.commit()
        return True

    # ------------------------------------------------------------------------------------------
    # Helpers.
    # ------------------------------------------------------------------------------------------

    def _schedule(self, first_sent_at: datetime, reminders_sent: int) -> datetime | None:
        return reminder_at(
            first_sent_at,
            reminders_sent,
            self.settings.reminder_schedule_days,
            start_hour=self.settings.reminder_start_hour,
            end_hour=self.settings.reminder_end_hour,
        )

    def _soonest(self, moment: datetime) -> datetime:
        return next_allowed(moment, start_hour=self.settings.reminder_start_hour, end_hour=self.settings.reminder_end_hour)

    def _advance(self, outreach: CaseOutreach) -> None:
        outreach.reminders_sent += 1
        if not outreach.reminders_enabled:
            outreach.next_reminder_at = None
            return
        upcoming = self._schedule(as_utc(outreach.first_sent_at), outreach.reminders_sent)  # type: ignore[arg-type]
        outreach.next_reminder_at = upcoming
        if upcoming is None:
            outreach.stopped_reason = "schedule_done"

    async def _new_link(self, case: Case, purpose: str) -> tuple[str, str, uuid.UUID, datetime | None]:
        base = self.settings.public_web_url.rstrip("/")
        if purpose == "intake":
            created = await IntakeService(self.session, self.container, self.scope).create_link(case.id)
            token, url = created.token, f"{base}{created.url_path}"
            link = await self.session.scalar(select(IntakeLink).where(IntakeLink.token_hash == hash_token(token)))
        else:
            created_signing = await PortalService(self.session, self.container, self.scope).create_link(case.id)
            url = created_signing.url
            token = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
            link = await self.session.scalar(select(SigningLink).where(SigningLink.token_hash == hash_token(token)))
        if link is None:
            raise NotFoundError("The new link was not found.")
        return token, url, link.id, as_utc(link.expires_at)

    async def _current_link(self, outreach: CaseOutreach) -> tuple[str, datetime | None]:
        token = open_secret(self.settings, outreach.token_sealed or "")
        base = self.settings.public_web_url.rstrip("/")
        if outreach.purpose == "intake":
            link = await self.session.get(IntakeLink, outreach.link_id)
            return f"{base}/upload/{token}", as_utc(link.expires_at) if link else None
        link_signing = await self.session.get(SigningLink, outreach.link_id)
        return f"{base}/sign/{token}", as_utc(link_signing.expires_at) if link_signing else None

    async def _stop_reason(self, case: Case, outreach: CaseOutreach) -> str | None:
        if case.status == CaseStatus.SIGNED:
            return "case_signed"
        now = utcnow()
        if outreach.purpose == "intake":
            link = await self.session.get(IntakeLink, outreach.link_id)
            if link is None or link.revoked_at is not None:
                return "link_replaced"
            expires_at = as_utc(link.expires_at)
            if expires_at is not None and expires_at <= now:
                return "link_closed"
            gap = self.cases._gap(case)
            if not gap.missing:
                return "done"
            return None
        signing = await self.session.get(SigningLink, outreach.link_id)
        if signing is None:
            return "link_replaced"
        if signing.completed_at is not None:
            return "done"
        if signing.revoked_at is not None:
            return "link_replaced" if signing.revoke_reason == "replaced" else "link_closed"
        if as_utc(signing.expires_at) <= now:  # type: ignore[operator]
            return "link_closed"
        return None

    async def _refresh_stop(self, case: Case, outreach: CaseOutreach) -> bool:
        reason = await self._stop_reason(case, outreach)
        if reason is None:
            return False
        outreach.stopped_reason = reason
        outreach.next_reminder_at = None
        return True

    async def _deliver(
        self,
        case: Case,
        outreach: CaseOutreach,
        kind: str,
        url: str,
        expires_at: datetime | None,
        office: str,
    ) -> tuple[OutboundMessage, str | None]:
        words = wording(
            outreach.purpose or "intake", kind, office=office, client=case.client_name, url=url, expires=expires_at
        )
        wa: str | None = None
        error: str | None = None
        if outreach.channel == "whatsapp":
            recipient = outreach.phone or ""
            wa = whatsapp_url(recipient, words.text)
            status = "handed_to_office"
            shown, masked = show_phone(recipient), mask_phone(recipient)
        else:
            recipient = outreach.email or ""
            shown, masked = recipient, mask_email(recipient)
            try:
                await self.email.send(
                    build_message(
                        self.settings,
                        to=recipient,
                        office=office,
                        subject=words.subject,
                        text=words.text,
                        url=url,
                        button=words.button,
                    )
                )
                status = "sent"
            except EmailError as exc:
                status, error = "failed", str(exc)
                logger.warning("Email to the client of case %s failed: %s", case.id, exc.__cause__ or exc)
        message = OutboundMessage(
            case_id=case.id,
            purpose=outreach.purpose or "intake",
            kind=kind,
            channel=outreach.channel or "email",
            recipient=shown,
            status=status,
            error=error,
            actor=self.scope.actor,
            created_at=utcnow(),
        )
        self.session.add(message)
        self.session.add(
            AuditLog(
                case_id=case.id,
                action=AuditAction.CLIENT_MESSAGE_SENT,
                actor=self.scope.actor,
                new_value={
                    "purpose": message.purpose,
                    "kind": kind,
                    "channel": message.channel,
                    "to": masked,
                    "status": status,
                },
            )
        )
        await self.session.flush()
        return message, wa

    async def _sent_today(self, case_id: uuid.UUID) -> int:
        since = utcnow() - timedelta(days=1)
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(OutboundMessage)
                .where(OutboundMessage.case_id == case_id, OutboundMessage.created_at >= since)
            )
            or 0
        )

    async def _check_daily_cap(self, case_id: uuid.UUID) -> None:
        if await self._sent_today(case_id) >= self.settings.max_messages_per_case_per_day:
            raise RateLimitError("נשלחו יותר מדי הודעות בתיק הזה היום. אפשר לנסות שוב מחר.")

    async def _office_name(self, case: Case) -> str:
        organization = await self.session.get(Organization, case.organization_id)
        return organization.name if organization is not None and organization.name else "המשרד"


_STOPPED_MESSAGE = {
    "case_signed": "התיק כבר חתום.",
    "done": "הלקוח כבר השלים את מה שהתבקש.",
    "link_replaced": "נוצר בינתיים קישור חדש. שלחו אותו מחדש.",
    "link_closed": "תוקף הקישור פג. שלחו קישור חדש.",
}
