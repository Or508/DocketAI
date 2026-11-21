from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import current_user
from app.core.rate_limit import client_ip
from app.domain.professions import profession as profession_of
from app.db.session import get_session
from app.models.organization import Organization
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.security_service import SecurityService

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str
    # The authenticator code or a recovery code, for an account with two-step login.
    code: str | None = Field(default=None, max_length=32)


class SecurityStatus(BaseModel):
    mfa_enabled: bool
    recovery_codes_left: int
    min_password_length: int


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class MfaSetup(BaseModel):
    secret: str
    otpauth_uri: str


class MfaCode(BaseModel):
    code: str = Field(max_length=32)


class MfaConfirmed(MfaCode):
    password: str = Field(max_length=256)


class RecoveryCodes(BaseModel):
    recovery_codes: list[str]


class UserRead(BaseModel):
    id: UUID
    email: str
    display_name: str
    # "owner" manages people and office settings; "staff" works on cases.
    role: str
    organization_id: UUID
    organization_name: str
    # The office's profession and the words its screens use.
    profession: str
    profession_label_he: str
    client_term_he: str
    case_term_he: str
    # When the office is a public demo, the moment it is deleted. Null for a real office.
    demo_expires_at: datetime | None = None


class LoginResponse(BaseModel):
    token: str
    expires_at: datetime
    user: UserRead


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    _scheme, _, token = header.partition(" ")
    return token.strip()


async def _user_read(session: AsyncSession, user: User) -> UserRead:
    organization = await session.get(Organization, user.organization_id)
    kind = profession_of(organization.profession if organization is not None else None)
    return UserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        organization_id=user.organization_id,
        organization_name=organization.name if organization is not None else "",
        profession=kind.key,
        profession_label_he=kind.label_he,
        client_term_he=kind.client_he,
        case_term_he=kind.case_he,
        demo_expires_at=organization.demo_expires_at if organization is not None else None,
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)
) -> LoginResponse:
    service = AuthService(session, get_settings())
    token, expires_at, user = await service.login(payload.email, payload.password, payload.code, client_ip(request))
    return LoginResponse(token=token, expires_at=expires_at, user=await _user_read(session, user))


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    _user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await AuthService(session, get_settings()).logout(_bearer(request))
    return Response(status_code=204)


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> UserRead:
    return await _user_read(session, user)


def _security(user: User, session: AsyncSession) -> SecurityService:
    return SecurityService(session, get_settings(), user)


@router.get("/security", response_model=SecurityStatus)
async def security_status(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> SecurityStatus:
    return SecurityStatus(**_security(user, session).status())


@router.post("/password", status_code=204)
async def change_password(
    payload: PasswordChange,
    request: Request,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """A new password. Every other signed-in device of this user is signed out."""
    await _security(user, session).change_password(payload.current_password, payload.new_password, _bearer(request))
    return Response(status_code=204)


@router.post("/mfa/setup", response_model=MfaSetup)
async def mfa_setup(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)) -> MfaSetup:
    """A secret for the authenticator app, as text and as an otpauth:// link for a QR code."""
    return MfaSetup(**await _security(user, session).start_mfa())


@router.post("/mfa/enable", response_model=RecoveryCodes)
async def mfa_enable(
    payload: MfaCode, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> RecoveryCodes:
    """Turn two-step login on with a code from the app. The recovery codes are shown only now."""
    return RecoveryCodes(recovery_codes=await _security(user, session).confirm_mfa(payload.code))


@router.post("/mfa/disable", status_code=204)
async def mfa_disable(
    payload: MfaConfirmed, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> Response:
    await _security(user, session).disable_mfa(payload.password, payload.code)
    return Response(status_code=204)


@router.post("/mfa/recovery-codes", response_model=RecoveryCodes)
async def mfa_recovery_codes(
    payload: MfaConfirmed, user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> RecoveryCodes:
    """New recovery codes; the old ones stop working."""
    return RecoveryCodes(recovery_codes=await _security(user, session).renew_recovery_codes(payload.password, payload.code))
