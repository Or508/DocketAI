import asyncio
import json
from uuid import UUID

from app.db.session import session_scope
from app.models.case import Case

_TERMINAL = {"awaiting_input", "ready_for_signature", "signed", "failed", "draft"}


async def iter_case_progress(case_id: UUID):
    last: str | None = None
    for _ in range(400):
        async with session_scope() as session:
            case = await session.get(Case, case_id)
            if case is None:
                yield 'event: error\ndata: {"detail":"Case not found."}\n\n'
                return
            payload = {
                "stage": case.pipeline_stage or "draft",
                "completed": int(case.pipeline_completed or 0),
                "total": int(case.pipeline_total or 0),
                "message": case.pipeline_message or "",
                "status": case.status.value,
            }
        encoded = json.dumps(payload, separators=(",", ":"))
        if encoded != last:
            yield f"event: progress\ndata: {encoded}\n\n"
            last = encoded
            if payload["stage"] in _TERMINAL:
                yield "event: done\ndata: {}\n\n"
                return
        else:
            yield ": keepalive\n\n"
        await asyncio.sleep(1)
    yield "event: done\ndata: {}\n\n"
