import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

from pydantic import BaseModel

from app.core.container import Container
from app.db.session import session_scope
from app.domain.case_scope import CaseScope
from app.schemas.chat import ChatRequest
from app.schemas.events import StreamError
from app.services.case_service import CaseService
from app.schemas.process import ValueSource

logger = logging.getLogger(__name__)
_DONE = object()


def _frame(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


async def _pump(source: AsyncIterator[str], queue: asyncio.Queue) -> None:
    try:
        async for token in source:
            await queue.put(token)
        await queue.put(_DONE)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await queue.put(exc)


async def iter_chat_stream(
    case_id: UUID,
    payload: ChatRequest,
    container: Container,
    scope: CaseScope,
    *,
    render: Callable[[CaseService, UUID], Awaitable[BaseModel]] | None = None,
    reject_if_signed: bool = False,
    source: ValueSource = "office",
) -> AsyncIterator[str]:
    try:
        async with session_scope() as session:
            start = await CaseService(session, container, scope).chat_begin(
                case_id,
                payload,
                reject_if_signed=reject_if_signed,
                source=source,
            )
        draft = start.turn.reply
        streamed = ""
        failed = False
        queue: asyncio.Queue = asyncio.Queue()
        pump = asyncio.create_task(_pump(container.chat.stream_reply(start.turn), queue))
        timeout = container.settings.chat_stream_idle_timeout_seconds
        try:
            while True:
                item = await asyncio.wait_for(queue.get(), timeout)
                if item is _DONE:
                    break
                if isinstance(item, Exception):
                    raise item
                streamed += item
                yield _frame("delta", json.dumps(item, ensure_ascii=False))
        except Exception:
            logger.warning("Reply streaming fell back to the recorded reply", exc_info=True)
            failed = True
        finally:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)
        final = draft if failed or not streamed.strip() else streamed.strip()
        if failed and streamed:
            yield _frame("replace", json.dumps(draft, ensure_ascii=False))
        elif not streamed.strip():
            yield _frame("delta", json.dumps(draft, ensure_ascii=False))
        async with session_scope() as session:
            service = CaseService(session, container, scope)
            workspace = await service.chat_finish(case_id, start.stamp, draft, final)
            frame = workspace if render is None else await render(service, case_id)
        yield _frame("workspace", frame.model_dump_json())
    except Exception:
        logger.exception("Chat stream failed for case %s", case_id)
        yield _frame(
            "error",
            StreamError(detail="The clerk could not finish this reply.").model_dump_json(),
        )
