import asyncio
import logging
from uuid import UUID

logger = logging.getLogger(__name__)


async def enqueue_case_processing(case_id: UUID) -> str | None:
    from app.core.config import get_settings

    settings = get_settings()
    if not settings.queue_enabled:
        return None
    pool = None
    try:
        from arq import create_pool
        from arq.connections import RedisSettings

        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        pool = await asyncio.wait_for(create_pool(redis_settings), timeout=2.5)
        job = await pool.enqueue_job("process_case", str(case_id))
        return job.job_id if job else None
    except Exception:
        logger.warning("Redis unavailable; the upload will be processed in-process")
        return None
    finally:
        if pool is not None:
            await pool.close()
