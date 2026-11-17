from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import office_scope
from app.db.session import get_session
from app.domain.case_scope import CaseScope
from app.schemas.audit import AuditCenter
from app.services.audit_center import MAX_LIMIT, audit_center

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=AuditCenter)
async def audit(
    action: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=MAX_LIMIT),
    session: AsyncSession = Depends(get_session),
    scope: CaseScope = Depends(office_scope),
) -> AuditCenter:
    """The office's audit events across all its cases, newest first, with summary counters."""
    return await audit_center(session, scope, action=action, q=q, limit=limit)
