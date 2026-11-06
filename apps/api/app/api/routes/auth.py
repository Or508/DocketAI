from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import current_user
from app.db.session import get_session
from app.models.organization import Organization
from app.models.user import User
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class UserRead(BaseModel):
    id: UUID
    email: str
    display_name: str
    organization_id: UUID
    organization_name: str


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
    return UserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        organization_id=user.organization_id,
        organization_name=organization.name if organization is not None else "",
    )


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_session)) -> LoginResponse:
    service = AuthService(session, get_settings())
    token, expires_at, user = await service.login(payload.email, payload.password)
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
