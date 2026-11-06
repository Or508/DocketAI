from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.deps import get_office_link_service
from app.schemas.portal import SigningLinkCreated, SigningLinkRead
from app.services.portal_service import PortalService

router = APIRouter(prefix="/cases", tags=["signing-links"])


@router.post("/{case_id}/signing-links", response_model=SigningLinkCreated, status_code=201)
async def create_signing_link(
    case_id: UUID,
    service: PortalService = Depends(get_office_link_service),
) -> SigningLinkCreated:
    return await service.create_link(case_id)


@router.get("/{case_id}/signing-link", response_model=SigningLinkRead)
async def read_signing_link(
    case_id: UUID,
    service: PortalService = Depends(get_office_link_service),
) -> SigningLinkRead:
    return await service.current(case_id)


@router.delete("/{case_id}/signing-link", status_code=204)
async def revoke_signing_link(
    case_id: UUID,
    service: PortalService = Depends(get_office_link_service),
) -> None:
    await service.revoke_link(case_id)
