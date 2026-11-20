from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.container import Container
from app.core.deps import get_container, office_scope
from app.db.session import get_session
from app.domain.case_scope import CaseScope
from app.schemas.outreach import DueReminder, OutreachSendRequest, OutreachSent, OutreachState, RemindersUpdate
from app.services.outreach_service import OutreachService

router = APIRouter(tags=["outreach"])


def get_outreach_service(
    session: AsyncSession = Depends(get_session),
    container: Container = Depends(get_container),
    scope: CaseScope = Depends(office_scope),
) -> OutreachService:
    return OutreachService(session, container, scope)


@router.post("/cases/{case_id}/outreach/send", response_model=OutreachSent, status_code=201)
async def send_to_client(
    case_id: UUID, payload: OutreachSendRequest, service: OutreachService = Depends(get_outreach_service)
) -> OutreachSent:
    """A fresh link to the client by email (sent now) or WhatsApp (a link the office opens and sends).
    The link the case had before stops working."""
    return await service.send(case_id, payload)


@router.get("/cases/{case_id}/outreach", response_model=OutreachState)
async def outreach_state(case_id: UUID, service: OutreachService = Depends(get_outreach_service)) -> OutreachState:
    return await service.state(case_id)


@router.put("/cases/{case_id}/outreach/reminders", response_model=OutreachState)
async def set_reminders(
    case_id: UUID, payload: RemindersUpdate, service: OutreachService = Depends(get_outreach_service)
) -> OutreachState:
    return await service.set_reminders(case_id, payload.enabled)


@router.post("/cases/{case_id}/outreach/remind", response_model=OutreachSent)
async def remind_now(case_id: UUID, service: OutreachService = Depends(get_outreach_service)) -> OutreachSent:
    """A reminder with the link already sent. By email it goes out now; by WhatsApp the office opens the link."""
    return await service.remind_now(case_id)


@router.get("/outreach/due", response_model=list[DueReminder])
async def due_reminders(service: OutreachService = Depends(get_outreach_service)) -> list[DueReminder]:
    """WhatsApp reminders whose time has come. The office sends each one with "remind"."""
    return await service.due_whatsapp()
