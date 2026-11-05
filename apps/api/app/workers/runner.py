import logging
from uuid import UUID

from app.core.container import Container
from app.db.session import session_scope
from app.services.case_service import CaseService

logger = logging.getLogger(__name__)


async def process_case_job(case_id: UUID, container: Container) -> None:
    try:
        async with session_scope() as session:
            service = CaseService(session, container)
            await service.run_ingestion(case_id)
    except Exception:
        logger.exception("Ingestion failed for case %s", case_id)
