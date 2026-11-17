from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import office_scope
from app.db.session import get_session
from app.domain.case_scope import CaseScope
from app.schemas.audit import AuditCenter
from app.core.time import utcnow
from app.services.audit_center import MAX_LIMIT, audit_center, export_csv

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


@router.get("/export.csv")
async def audit_export(
    action: str | None = Query(default=None, max_length=64),
    q: str | None = Query(default=None, max_length=120),
    session: AsyncSession = Depends(get_session),
    scope: CaseScope = Depends(office_scope),
) -> Response:
    """The same events `GET /audit` finds for these filters, as a CSV file the office can keep."""
    data = await export_csv(session, scope, action=action, q=q)
    filename = f"audit-log-{utcnow():%Y-%m-%d}.csv"
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
