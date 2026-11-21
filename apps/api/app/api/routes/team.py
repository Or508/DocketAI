"""The office's people. Every member sees the list; only an owner invites or changes anyone."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import current_user, require_owner
from app.db.session import get_session
from app.models.user import User
from app.services.team_service import InviteOutcome, Member, TeamService

router = APIRouter(prefix="/team", tags=["team"])

Role = Literal["owner", "staff"]


class MemberRead(BaseModel):
    id: UUID
    email: str
    display_name: str
    role: Role
    # active, invited (has not chosen a password yet), invite_expired, inactive (turned off).
    status: Literal["active", "invited", "invite_expired", "inactive"]
    is_you: bool
    mfa_enabled: bool
    created_at: datetime
    invite_expires_at: datetime | None


class InviteRequest(BaseModel):
    email: str = Field(max_length=320)
    display_name: str = Field(max_length=160)
    role: Role = "staff"


class InviteResult(BaseModel):
    member: MemberRead
    # The link itself, so the owner can pass it on (WhatsApp, in person) when email did not go out.
    invite_url: str
    email_sent: bool
    email_error: str | None


class MemberChange(BaseModel):
    role: Role | None = None
    is_active: bool | None = None
    display_name: str | None = Field(default=None, max_length=160)


def _read(member: Member, actor: User) -> MemberRead:
    user = member.user
    return MemberRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role if user.role in ("owner", "staff") else "staff",
        status=member.status,
        is_you=user.id == actor.id,
        mfa_enabled=bool(user.mfa_enabled),
        created_at=user.created_at,
        invite_expires_at=member.invite_expires_at,
    )


def _invite(outcome: InviteOutcome, actor: User) -> InviteResult:
    return InviteResult(
        member=_read(outcome.member, actor),
        invite_url=outcome.invite_url,
        email_sent=outcome.email_sent,
        email_error=outcome.email_error,
    )


@router.get("", response_model=list[MemberRead])
async def list_members(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[MemberRead]:
    members = await TeamService(session, get_settings(), user).members()
    return [_read(member, user) for member in members]


@router.post("/invite", response_model=InviteResult, status_code=201)
async def invite_member(
    payload: InviteRequest, user: User = Depends(require_owner), session: AsyncSession = Depends(get_session)
) -> InviteResult:
    """Add a colleague. They get an email with a link to choose their password."""
    outcome = await TeamService(session, get_settings(), user).invite(payload.email, payload.display_name, payload.role)
    return _invite(outcome, user)


@router.post("/{user_id}/resend-invite", response_model=InviteResult)
async def resend_invite(
    user_id: UUID, user: User = Depends(require_owner), session: AsyncSession = Depends(get_session)
) -> InviteResult:
    """A new invitation link. The previous one stops working."""
    return _invite(await TeamService(session, get_settings(), user).resend_invite(user_id), user)


@router.patch("/{user_id}", response_model=MemberRead)
async def change_member(
    user_id: UUID,
    payload: MemberChange,
    user: User = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> MemberRead:
    """Change a colleague's role or name, or turn the account off (signs them out at once) or on again."""
    member = await TeamService(session, get_settings(), user).update(
        user_id, role=payload.role, is_active=payload.is_active, display_name=payload.display_name
    )
    return _read(member, user)
