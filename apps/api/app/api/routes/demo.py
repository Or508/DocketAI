"""A public demo. Off unless DEMO_MODE is set, and then one click opens a private sandbox office."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.auth import LoginResponse, _user_read
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, RateLimitError
from app.core.rate_limit import allow_demo_start, client_ip
from app.db.session import get_session
from app.services.demo_service import DemoService

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoStart(BaseModel):
    scenario: Literal["law", "dental", "hr"]


class DemoInfo(BaseModel):
    enabled: bool
    whatsapp: str
    ttl_hours: int


@router.get("/info", response_model=DemoInfo)
async def info() -> DemoInfo:
    settings = get_settings()
    return DemoInfo(enabled=settings.demo_mode, whatsapp=settings.demo_whatsapp, ttl_hours=settings.demo_ttl_hours)


@router.post("/start", response_model=LoginResponse)
async def start(
    payload: DemoStart, request: Request, session: AsyncSession = Depends(get_session)
) -> LoginResponse:
    settings = get_settings()
    if not settings.demo_mode:
        raise NotFoundError("Not found")
    if not allow_demo_start(client_ip(request), settings.demo_starts_per_ip_per_day):
        raise RateLimitError("הגעתם למכסת הדמו להיום. אפשר לנסות שוב מחר.")
    token, expires_at, user = await DemoService(session, settings, request.app.state.container).start(payload.scenario)
    return LoginResponse(token=token, expires_at=expires_at, user=await _user_read(session, user))
