import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

import app.models  # noqa: F401
from app.api.router import api_router
from app.catalog.processes import PROCESSES
from app.core.config import get_settings
from app.core.container import build_container
from app.core.exceptions import AppError
from app.core.rate_limit import check_request
from app.db.base import Base
from app.db.compat import ensure_case_columns, ensure_default_organization
from app.db.session import get_engine, session_scope
from app.domain.enums import DocumentStatus
from app.models.document import Document
from app.services.seeding import seed_processes
from app.workers.runner import process_case_job

logger = logging.getLogger(__name__)


def _ensure_dirs(settings) -> None:
    if settings.storage_backend == "local":
        settings.resolved_storage_dir.mkdir(parents=True, exist_ok=True)
    settings.resolved_template_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite"):
        raw = settings.database_url.split("///", 1)[-1]
        if raw and raw != ":memory:":
            Path(raw).parent.mkdir(parents=True, exist_ok=True)


async def _resume_unread(container) -> None:
    """Read the files an earlier run stored and never finished, one case at a time."""
    try:
        async with session_scope() as session:
            rows = await session.scalars(
                select(Document.case_id)
                .where(Document.status.in_([DocumentStatus.UPLOADED, DocumentStatus.PROCESSING]))
                .distinct()
            )
            case_ids = list(rows)
        for case_id in case_ids:
            logger.info("Resuming unread files on case %s", case_id)
            await process_case_job(case_id, container)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Could not resume unread files")


async def _reminder_loop(container, every_seconds: int) -> None:
    """Email reminders that are due go out every few minutes. Each one is claimed first, so two processes never
    send the same reminder twice."""
    from app.workers.runner import send_due_reminders

    while True:
        await asyncio.sleep(every_seconds)
        try:
            sent = await send_due_reminders(container)
            if sent:
                logger.info("Sent %s client reminders", sent)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("The reminder round failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    _ensure_dirs(settings)
    container = build_container(settings)
    container.templates.ensure_templates(PROCESSES)
    app.state.container = container
    if settings.auto_create_schema:
        async with get_engine().begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    await ensure_case_columns()
    await ensure_default_organization()
    async with session_scope() as session:
        await seed_processes(session)
    resume = None
    if not settings.queue_enabled:
        # In-process work is lost when the API stops. Pick up what it left unread.
        resume = asyncio.create_task(_resume_unread(container))
    reminders = asyncio.create_task(_reminder_loop(container, settings.reminder_poll_seconds))
    yield
    reminders.cancel()
    if resume is not None and not resume.done():
        resume.cancel()


app = FastAPI(
    title="DocketAI",
    version="0.1.0",
    summary="Document ingestion, gap analysis, conversational form fill, and signing.",
    lifespan=lifespan,
)

class RateLimitMiddleware:
    """Plain ASGI, so the portal's event streams pass through untouched."""

    def __init__(self, inner) -> None:
        self.inner = inner

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            wait = check_request(Request(scope), get_settings())
            if wait is not None:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Try again shortly.", "code": "rate_limited"},
                    headers={"Retry-After": str(int(wait)), "Cache-Control": "no-store"},
                )
                await response(scope, receive, send)
                return
        await self.inner(scope, receive, send)


app.add_middleware(RateLimitMiddleware)


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
    )


app.include_router(api_router)
