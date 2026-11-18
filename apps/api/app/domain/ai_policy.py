"""Whether the office a piece of work belongs to lets its data reach an AI model.

An office can turn AI reading off (a clinic that must keep patient data in Israel, say). The work
that may call a model, reading a case's documents and the case chat, starts by stating whose
work it is; the model router and the learning store then refuse to send anything when the
answer is no. Without AI the office still gets deterministic reading of digital PDFs and sorting
by file name, and files the rest by hand.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import AsyncSession

_ALLOWED: ContextVar[bool] = ContextVar("office_ai_allowed", default=True)


def ai_allowed() -> bool:
    return _ALLOWED.get()


def set_ai_allowed(allowed: bool) -> None:
    """For the rest of this task, and any task it starts, model calls follow this answer."""
    _ALLOWED.set(allowed)


async def apply_office_policy(session: AsyncSession, organization_id: uuid.UUID | None) -> bool:
    from app.models.organization import Organization

    organization = await session.get(Organization, organization_id) if organization_id else None
    allowed = organization.ai_reading_enabled if organization is not None else True
    set_ai_allowed(bool(allowed))
    return bool(allowed)
