"""Public account links: joining an office by invitation, and "forgot my password".

The token travels in the request body, not the URL, so it stays out of access logs.
These paths share the login rate limit.
"""

from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.services.team_service import MIN_PASSWORD_LENGTH, AccountLinkService, send_quietly

router = APIRouter(prefix="/account", tags=["account"])

FORGOT_REPLY = "אם הכתובת רשומה אצלנו, נשלח אליה קישור לבחירת סיסמה חדשה."


class TokenRequest(BaseModel):
    token: str = Field(min_length=1, max_length=128)


class NewPassword(TokenRequest):
    password: str = Field(max_length=256)


class LinkInfo(BaseModel):
    purpose: Literal["invite", "reset"]
    email: str
    display_name: str
    organization_name: str
    min_password_length: int


class ForgotRequest(BaseModel):
    email: str = Field(max_length=320)


class ForgotReply(BaseModel):
    detail: str


@router.post("/link", response_model=LinkInfo)
async def describe_link(payload: TokenRequest, session: AsyncSession = Depends(get_session)) -> LinkInfo:
    """What an invitation or reset link is for, so the page can greet the person. 410 if it no longer works."""
    record, user, office = await AccountLinkService(session, get_settings()).describe(payload.token)
    return LinkInfo(
        purpose="invite" if record.purpose == "invite" else "reset",
        email=user.email,
        display_name=user.display_name,
        organization_name=office,
        min_password_length=MIN_PASSWORD_LENGTH,
    )


@router.post("/invite/accept", status_code=204)
async def accept_invite(payload: NewPassword, session: AsyncSession = Depends(get_session)) -> Response:
    """Choose a password and join the office. The person then signs in as usual."""
    await AccountLinkService(session, get_settings()).accept_invite(payload.token, payload.password)
    return Response(status_code=204)


@router.post("/password/forgot", response_model=ForgotReply, status_code=202)
async def forgot_password(
    payload: ForgotRequest, background: BackgroundTasks, session: AsyncSession = Depends(get_session)
) -> ForgotReply:
    """The same answer whether or not the address has an account. The email leaves after the answer."""
    settings = get_settings()
    message = await AccountLinkService(session, settings).request_reset(payload.email)
    if message is not None:
        background.add_task(send_quietly, settings, message)
    return ForgotReply(detail=FORGOT_REPLY)


@router.post("/password/reset", status_code=204)
async def reset_password(payload: NewPassword, session: AsyncSession = Depends(get_session)) -> Response:
    """Set the new password. Every signed-in device of that account is signed out. Two-step login stays on."""
    await AccountLinkService(session, get_settings()).reset_password(payload.token, payload.password)
    return Response(status_code=204)
