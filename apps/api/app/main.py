import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

import app.models  # noqa: F401
from app.api.router import api_router
from app.catalog.processes import PROCESSES
from app.core.config import get_settings
from app.core.container import build_container
from app.core.exceptions import AppError
from app.db.base import Base
from app.db.compat import ensure_case_columns, ensure_default_organization
from app.db.session import get_engine, session_scope
from app.services.seeding import seed_processes

logger = logging.getLogger(__name__)


def _ensure_dirs(settings) -> None:
    if settings.storage_backend == "local":
        settings.resolved_storage_dir.mkdir(parents=True, exist_ok=True)
    settings.resolved_template_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite"):
        raw = settings.database_url.split("///", 1)[-1]
        if raw and raw != ":memory:":
            Path(raw).parent.mkdir(parents=True, exist_ok=True)


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
    yield


app = FastAPI(
    title="DocketAI",
    version="0.1.0",
    summary="Document ingestion, gap analysis, conversational form fill, and signing.",
    lifespan=lifespan,
)

@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
    )


app.include_router(api_router)
