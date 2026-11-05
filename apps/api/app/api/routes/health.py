from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    database = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"
    settings = get_settings()
    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "gemini_configured": bool(settings.gemini_api_key),
        "queue_enabled": settings.queue_enabled,
    }
