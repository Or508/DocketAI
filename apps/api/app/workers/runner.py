import logging
from uuid import UUID

from app.core.container import Container
from app.db.session import session_scope
from app.domain.case_scope import CaseScope
from app.services.case_service import CaseService

logger = logging.getLogger(__name__)


async def process_case_job(case_id: UUID, container: Container) -> None:
    try:
        async with session_scope() as session:
            service = CaseService(session, container, CaseScope.system())
            await service.run_ingestion(case_id)
    except Exception:
        logger.exception("Ingestion failed for case %s", case_id)


async def send_due_reminders(container: Container) -> int:
    """One round of client email reminders across every office. Each reminder is claimed before it is sent."""
    from app.services.outreach_service import OutreachService

    async with session_scope() as session:
        return await OutreachService(session, container, CaseScope.system()).send_due_emails()
