from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.container import Container
from app.core.exceptions import NotFoundError, UnauthorizedError
from app.db.session import get_session
from app.domain.case_scope import CaseScope
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.case_service import CaseService
from app.services.portal_service import PortalService


def get_container(request: Request) -> Container:
    return request.app.state.container


def _bearer(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError()
    return token.strip()


async def current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    token = _bearer(request)
    return await AuthService(session, get_settings()).resolve_session(token)


def office_scope(user: User = Depends(current_user)) -> CaseScope:
    return CaseScope.office(user.organization_id, user.id)


def get_case_service(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    scope: CaseScope = Depends(office_scope),
) -> CaseService:
    return CaseService(session, container, scope)


def get_office_link_service(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    scope: CaseScope = Depends(office_scope),
) -> PortalService:
    return PortalService(session, container, scope)


def get_portal_service(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> PortalService:
    return PortalService(session, container, CaseScope.system())


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise NotFoundError("This link is no longer active.")
    return token.strip()
