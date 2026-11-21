"""The office's people: inviting a colleague, roles, turning an account off, and "forgot my password".

Account links (invite, reset) work once. Only a hash of each token is kept. Messages here are in
Hebrew because the screens show them as they are.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, GoneError, NotFoundError
from app.core.time import utcnow
from app.domain.signing_links import as_utc
from app.models.account_token import AccountToken
from app.models.organization import Organization
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth_service import hash_password
from app.services.demo_guard import is_demo, refuse_demo_email
from app.services.email_sender import EmailError, EmailSender, build_message

logger = logging.getLogger(__name__)

ROLES = ("owner", "staff")
INVITE = "invite"
RESET = "reset"
MIN_PASSWORD_LENGTH = 12
# A second "forgot my password" within this window sends nothing new; the first link still works.
RESET_RESEND_SECONDS = 120

_LINK_GONE = "הקישור כבר לא פעיל. אפשר לבקש קישור חדש."
_WEAK = f"בחרו סיסמה של {MIN_PASSWORD_LENGTH} תווים לפחות."


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise BadRequestError(_WEAK, code="weak_password")


@dataclass
class Member:
    user: User
    status: str  # active, invited, invite_expired, inactive
    invite_expires_at: datetime | None


@dataclass
class InviteOutcome:
    member: Member
    invite_url: str
    email_sent: bool
    email_error: str | None


async def _close_open_tokens(session: AsyncSession, user_id: uuid.UUID, purpose: str | None = None) -> None:
    query = update(AccountToken).where(AccountToken.user_id == user_id, AccountToken.used_at.is_(None))
    if purpose is not None:
        query = query.where(AccountToken.purpose == purpose)
    await session.execute(query.values(used_at=utcnow()))


async def _sign_out_everywhere(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


async def _new_token(session: AsyncSession, user: User, purpose: str, lifetime: timedelta) -> tuple[str, datetime]:
    await _close_open_tokens(session, user.id, purpose)
    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + lifetime
    session.add(AccountToken(user_id=user.id, purpose=purpose, token_hash=_hash(token), expires_at=expires_at))
    return token, expires_at


class TeamService:
    """What a signed-in member sees and, for an owner, changes about the office's people."""

    def __init__(self, session: AsyncSession, settings: Settings, actor: User) -> None:
        self.session = session
        self.settings = settings
        self.actor = actor

    async def members(self) -> list[Member]:
        users = list(
            await self.session.scalars(
                select(User).where(User.organization_id == self.actor.organization_id).order_by(User.created_at)
            )
        )
        invites = await self._invite_state([user.id for user in users])
        return [self._member(user, invites.get(user.id)) for user in users]

    async def invite(self, email: str, display_name: str, role: str) -> InviteOutcome:
        normalized = email.strip().lower()
        name = display_name.strip()
        if "@" not in normalized or "." not in normalized.partition("@")[2] or len(normalized) > 320:
            raise BadRequestError("כתובת האימייל לא תקינה.", code="bad_email")
        if not name:
            raise BadRequestError("כתבו את שם העובד.", code="missing_name")
        self._check_role(role)
        refuse_demo_email(await self.session.get(Organization, self.actor.organization_id))
        existing = await self.session.scalar(select(User).where(User.email == normalized))
        if existing is not None:
            if existing.organization_id == self.actor.organization_id:
                raise ConflictError("העובד כבר במשרד. אפשר לשלוח לו את ההזמנה שוב מהרשימה.", code="already_member")
            # Another office's account: say only that the address is taken.
            raise ConflictError("לכתובת הזו כבר יש חשבון.", code="email_taken")
        user = User(
            organization_id=self.actor.organization_id,
            email=normalized,
            # Nobody knows this password. The colleague chooses one through the link.
            password_hash=await asyncio.to_thread(hash_password, secrets.token_urlsafe(32)),
            display_name=name[:160],
            role=role,
        )
        self.session.add(user)
        await self.session.flush()
        return await self._send_invite(user)

    async def resend_invite(self, user_id: uuid.UUID) -> InviteOutcome:
        refuse_demo_email(await self.session.get(Organization, self.actor.organization_id))
        user = await self._colleague(user_id)
        invites = await self._invite_state([user.id])
        if user.id not in invites:
            raise ConflictError("העובד כבר הצטרף למשרד.", code="already_joined")
        if not user.is_active:
            raise ConflictError("החשבון כבוי. הפעילו אותו לפני שליחת הזמנה.", code="inactive")
        return await self._send_invite(user)

    async def update(
        self, user_id: uuid.UUID, *, role: str | None, is_active: bool | None, display_name: str | None
    ) -> Member:
        user = await self._colleague(user_id)
        if role is not None:
            self._check_role(role)
        if is_active is False and user.id == self.actor.id:
            raise BadRequestError("אי אפשר לכבות את החשבון שלך.", code="self_deactivate")
        loses_owner = user.role == "owner" and user.is_active and (
            (role is not None and role != "owner") or is_active is False
        )
        if loses_owner and await self._active_owners() <= 1:
            raise ConflictError("למשרד חייב להיות לפחות מנהל פעיל אחד.", code="last_owner")
        if display_name is not None:
            name = display_name.strip()
            if not name:
                raise BadRequestError("כתבו את שם העובד.", code="missing_name")
            user.display_name = name[:160]
        if role is not None:
            user.role = role
        if is_active is not None and is_active != user.is_active:
            user.is_active = is_active
            if not is_active:
                await _sign_out_everywhere(self.session, user.id)
                await _close_open_tokens(self.session, user.id, RESET)
        await self.session.commit()
        logger.info(
            "Organization %s: user %s changed %s (role=%s, active=%s)",
            self.actor.organization_id, self.actor.id, user.id, user.role, user.is_active,
        )
        invites = await self._invite_state([user.id])
        return self._member(user, invites.get(user.id))

    async def _send_invite(self, user: User) -> InviteOutcome:
        hours = self.settings.invite_link_ttl_hours
        token, expires_at = await _new_token(self.session, user, INVITE, timedelta(hours=hours))
        await self.session.commit()
        office = await self._office_name()
        url = f"{self.settings.public_web_url.rstrip('/')}/join/{token}"
        text = (
            f"שלום {user.display_name},\n"
            f"{self.actor.display_name} הזמין/ה אותך להצטרף למשרד {office}.\n"
            f"כדי להצטרף, בחרו סיסמה בקישור הבא. הקישור בתוקף {hours} שעות.\n"
            f"{url}"
        )
        message = build_message(
            self.settings, to=user.email, office=office, subject=f"הזמנה להצטרף ל{office}",
            text=text, url=url, button="הצטרפות למשרד",
        )
        sent, error = True, None
        try:
            await EmailSender(self.settings).send(message)
        except EmailError as exc:
            # The office can still pass the link on by hand.
            sent, error = False, str(exc)
        logger.info("Organization %s: user %s invited %s (email sent: %s)", user.organization_id, self.actor.id, user.id, sent)
        return InviteOutcome(Member(user, "invited", expires_at), url, sent, error)

    async def _colleague(self, user_id: uuid.UUID) -> User:
        user = await self.session.get(User, user_id)
        if user is None or user.organization_id != self.actor.organization_id:
            raise NotFoundError("העובד לא נמצא.")
        return user

    async def _active_owners(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count()).select_from(User).where(
                    User.organization_id == self.actor.organization_id,
                    User.role == "owner",
                    User.is_active.is_(True),
                )
            )
            or 0
        )

    async def _invite_state(self, user_ids: list[uuid.UUID]) -> dict[uuid.UUID, datetime]:
        """Members who have not joined yet, with when their newest invitation expires.

        A colleague has joined once their newest invitation was used. Sending it again closes the older one.
        """
        if not user_ids:
            return {}
        newest: dict[uuid.UUID, AccountToken] = {}
        for row in await self.session.scalars(
            select(AccountToken).where(AccountToken.user_id.in_(user_ids), AccountToken.purpose == INVITE)
        ):
            current = newest.get(row.user_id)
            if current is None or as_utc(row.created_at) > as_utc(current.created_at):
                newest[row.user_id] = row
        return {user_id: as_utc(row.expires_at) for user_id, row in newest.items() if row.used_at is None}

    def _member(self, user: User, invite_expires_at: datetime | None) -> Member:
        if not user.is_active:
            return Member(user, "inactive", None)
        if invite_expires_at is None:
            return Member(user, "active", None)
        if invite_expires_at <= utcnow():
            return Member(user, "invite_expired", invite_expires_at)
        return Member(user, "invited", invite_expires_at)

    def _check_role(self, role: str) -> None:
        if role not in ROLES:
            raise BadRequestError("תפקיד לא מוכר.", code="bad_role")

    async def _office_name(self) -> str:
        organization = await self.session.get(Organization, self.actor.organization_id)
        return organization.name if organization is not None else ""


class AccountLinkService:
    """The public side of account links: joining an office and choosing a new password."""

    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def describe(self, token: str) -> tuple[AccountToken, User, str]:
        record = await self._open(token)
        user = await self.session.get(User, record.user_id)
        assert user is not None
        organization = await self.session.get(Organization, user.organization_id)
        return record, user, organization.name if organization is not None else ""

    async def accept_invite(self, token: str, password: str) -> None:
        await self._set_password(token, password, INVITE)

    async def reset_password(self, token: str, password: str) -> None:
        await self._set_password(token, password, RESET)

    async def request_reset(self, email: str) -> object | None:
        """The message to send, or None. The caller answers the same way either way."""
        normalized = email.strip().lower()
        user = await self.session.scalar(select(User).where(User.email == normalized))
        if user is None or not user.is_active:
            return None
        # A demo office has no real mailbox, and a password email must never leave it.
        organization = await self.session.get(Organization, user.organization_id)
        if is_demo(organization) or user.email.endswith("@demo.invalid"):
            return None
        recent = await self.session.scalar(
            select(AccountToken).where(
                AccountToken.user_id == user.id,
                AccountToken.purpose == RESET,
                AccountToken.used_at.is_(None),
                AccountToken.created_at > utcnow() - timedelta(seconds=RESET_RESEND_SECONDS),
            )
        )
        if recent is not None:
            return None
        minutes = self.settings.password_reset_minutes
        token, _expires = await _new_token(self.session, user, RESET, timedelta(minutes=minutes))
        await self.session.commit()
        organization = await self.session.get(Organization, user.organization_id)
        office = organization.name if organization is not None else ""
        url = f"{self.settings.public_web_url.rstrip('/')}/reset-password/{token}"
        text = (
            f"שלום {user.display_name},\n"
            f"ביקשת לבחור סיסמה חדשה לחשבון שלך ב{office}.\n"
            f"הקישור בתוקף {minutes} דקות. אם לא ביקשת, אפשר להתעלם מההודעה, והסיסמה שלך לא תשתנה.\n"
            f"{url}"
        )
        logger.info("Password reset requested for user %s", user.id)
        return build_message(
            self.settings, to=user.email, office=office, subject="בחירת סיסמה חדשה",
            text=text, url=url, button="בחירת סיסמה חדשה",
        )

    async def _open(self, token: str, purpose: str | None = None) -> AccountToken:
        record = await self.session.scalar(select(AccountToken).where(AccountToken.token_hash == _hash(token.strip())))
        if (
            record is None
            or record.used_at is not None
            or as_utc(record.expires_at) <= utcnow()
            or (purpose is not None and record.purpose != purpose)
        ):
            raise GoneError(_LINK_GONE)
        user = await self.session.get(User, record.user_id)
        if user is None or not user.is_active:
            raise GoneError(_LINK_GONE)
        return record

    async def _set_password(self, token: str, password: str, purpose: str) -> None:
        _check_password(password)
        record = await self._open(token, purpose)
        user = await self.session.get(User, record.user_id)
        assert user is not None
        user.password_hash = await asyncio.to_thread(hash_password, password)
        user.failed_logins = 0
        user.locked_until = None
        record.used_at = utcnow()
        await self.session.flush()
        # A new password closes every other open link and signs the account out everywhere.
        # An invitation link stays marked as used, which is how the office sees the colleague joined.
        await _close_open_tokens(self.session, user.id, RESET)
        await _sign_out_everywhere(self.session, user.id)
        await self.session.commit()
        logger.info("User %s set a password through a %s link", user.id, purpose)


async def send_quietly(settings: Settings, message) -> None:
    """For "forgot my password": runs after the answer, so the answer takes the same time for any address."""
    try:
        await EmailSender(settings).send(message)
    except EmailError:
        logger.warning("A password reset email was not sent", exc_info=True)
