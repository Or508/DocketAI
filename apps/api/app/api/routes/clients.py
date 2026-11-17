from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_case_service, office_scope
from app.db.session import get_session
from app.domain.case_scope import CaseScope
from app.schemas.clients import ClientRead, QuickCaseRequest
from app.schemas.workspace import CaseWorkspace
from app.services.case_service import CaseService
from app.services.clients import list_clients

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=list[ClientRead])
async def clients(
    session: AsyncSession = Depends(get_session),
    scope: CaseScope = Depends(office_scope),
) -> list[ClientRead]:
    """The office's clients, each with their details, their cases and the documents a new case can reuse."""
    return await list_clients(session, scope)


@router.post("/quick-case", response_model=CaseWorkspace, status_code=status.HTTP_201_CREATED)
async def quick_case(
    payload: QuickCaseRequest,
    service: CaseService = Depends(get_case_service),
) -> CaseWorkspace:
    """Open a new case for the client of an existing case, reusing the documents already on file."""
    return await service.quick_case(payload.source_case_id, payload.process_type)
