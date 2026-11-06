from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.exceptions import NotFoundError
from app.db.session import get_session
from app.services.case_service import CaseService
from app.services.portal_service import PortalService


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_case_service(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> CaseService:
    return CaseService(session, container)


def get_portal_service(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> PortalService:
    return PortalService(session, container)


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise NotFoundError("This link is no longer active.")
    return token.strip()
