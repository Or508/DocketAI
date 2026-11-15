from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.deps import get_container, office_scope
from app.db.session import get_session
from app.domain.case_scope import CaseScope
from app.schemas.templates import TemplateRead
from app.services.template_catalog import list_templates

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=list[TemplateRead])
async def templates(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    scope: CaseScope = Depends(office_scope),
) -> list[TemplateRead]:
    return await list_templates(session, container.settings, scope)
