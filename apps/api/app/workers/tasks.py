from uuid import UUID

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.container import build_container
from app.workers.runner import process_case_job

_settings = get_settings()


async def startup(ctx: dict) -> None:
    ctx["container"] = build_container()


async def shutdown(ctx: dict) -> None:
    ctx.pop("container", None)


async def process_case(ctx: dict, case_id: str) -> None:
    await process_case_job(UUID(case_id), ctx["container"])


class WorkerSettings:
    functions = [process_case]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    max_tries = 1
    job_timeout = 600
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)
