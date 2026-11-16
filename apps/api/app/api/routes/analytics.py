from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import office_scope
from app.db.session import get_session
from app.domain.case_scope import CaseScope
from app.schemas.analytics import AnalyticsSummary
from app.services import analytics

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary", response_model=AnalyticsSummary)
async def analytics_summary(
    response: Response,
    session: AsyncSession = Depends(get_session),
    scope: CaseScope = Depends(office_scope),
) -> AnalyticsSummary:
    response.headers["Cache-Control"] = "no-store"
    return await analytics.summary(session, scope)


@router.get("/export.csv")
async def analytics_export(
    session: AsyncSession = Depends(get_session),
    scope: CaseScope = Depends(office_scope),
) -> Response:
    data = await analytics.export_csv(session, scope)
    return Response(
        content=data,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{analytics.CSV_FILENAME}"',
            "Cache-Control": "no-store",
        },
    )
