from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.db.session import get_session
from app.services.case_service import CaseService


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_case_service(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
) -> CaseService:
    return CaseService(session, container)
