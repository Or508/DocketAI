import asyncio
from uuid import UUID

from app.db.session import session_scope
from app.domain.case_scope import CaseScope, case_query
from app.models.case import Case
from app.schemas.events import CaseProgressEvent, StreamError

_TERMINAL = {"awaiting_input", "ready_for_signature", "signed", "failed", "draft"}


async def iter_case_progress(case_id: UUID, scope: CaseScope):
    last: str | None = None
    for _ in range(400):
        async with session_scope() as session:
            case = await session.scalar(case_query(scope).where(Case.id == case_id))
            if case is None:
                yield f"event: error\ndata: {StreamError(detail='Case not found.').model_dump_json()}\n\n"
                return
            stage = case.pipeline_stage or "draft"
            if stage not in _TERMINAL and stage not in {"parsing", "classifying", "auditing"}:
                stage = "draft"
            payload = CaseProgressEvent(
                stage=stage,  # type: ignore[arg-type]
                completed=int(case.pipeline_completed or 0),
                total=int(case.pipeline_total or 0),
                message=case.pipeline_message or "",
                status=case.status,
            )
        encoded = payload.model_dump_json()
        if encoded != last:
            yield f"event: progress\ndata: {encoded}\n\n"
            last = encoded
            if payload.stage in _TERMINAL:
                yield "event: done\ndata: {}\n\n"
                return
        else:
            yield ": keepalive\n\n"
        await asyncio.sleep(1)
    yield "event: done\ndata: {}\n\n"
