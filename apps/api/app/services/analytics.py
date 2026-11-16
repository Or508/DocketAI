"""Office metrics and the case report. Everything is read through the caller's case scope."""

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.domain.case_scope import CaseScope, case_query
from app.domain.enums import CaseStatus
from app.domain.signing_links import as_utc
from app.models.case import Case
from app.models.process_definition import ProcessDefinition
from app.models.signing_link import SigningLink
from app.schemas.analytics import AnalyticsSummary, ProcessBreakdown

CSV_FILENAME = "office_cases_report.csv"
CSV_COLUMNS = ("case_id", "client_name", "process_type", "status", "created_at", "signed_at", "verification_id")
_WAITING_STAGE = "ready_for_signature"
# A spreadsheet runs a cell that starts with one of these as a formula.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class _Row:
    id: UUID
    client_name: str | None
    process_type: str
    status: CaseStatus
    created_at: datetime | None
    signed_at: datetime | None
    verification_id: str | None
    field_values: dict
    field_sources: dict
    pipeline_stage: str


async def _rows(session: AsyncSession, scope: CaseScope) -> list[_Row]:
    stmt = (
        case_query(scope)
        .join(ProcessDefinition, ProcessDefinition.id == Case.process_definition_id)
        .with_only_columns(
            Case.id,
            Case.client_name,
            ProcessDefinition.key,
            Case.status,
            Case.created_at,
            Case.signed_at,
            Case.signer_verification_id,
            Case.field_values,
            Case.field_sources,
            Case.pipeline_stage,
        )
        .order_by(Case.created_at.desc(), Case.id)
    )
    return [
        _Row(
            id=row[0],
            client_name=row[1],
            process_type=row[2],
            status=CaseStatus(row[3]),
            created_at=as_utc(row[4]),
            signed_at=as_utc(row[5]),
            verification_id=row[6],
            field_values=row[7] if isinstance(row[7], dict) else {},
            field_sources=row[8] if isinstance(row[8], dict) else {},
            pipeline_stage=str(row[9] or ""),
        )
        for row in (await session.execute(stmt)).all()
    ]


async def _open_links(session: AsyncSession, case_ids: list[UUID]) -> set[UUID]:
    if not case_ids:
        return set()
    found = await session.scalars(
        select(SigningLink.case_id).where(
            SigningLink.case_id.in_(case_ids),
            SigningLink.revoked_at.is_(None),
            SigningLink.completed_at.is_(None),
            SigningLink.expires_at > utcnow(),
        )
    )
    return set(found)


async def summary(session: AsyncSession, scope: CaseScope) -> AnalyticsSummary:
    rows = await _rows(session, scope)
    linked = await _open_links(session, [row.id for row in rows if row.status != CaseStatus.SIGNED])
    processes = (await session.scalars(select(ProcessDefinition.key).order_by(ProcessDefinition.key))).all()
    breakdown = {key: [0, 0, 0] for key in processes}  # filling, waiting, signed
    by_status: dict[str, int] = {}
    hours: list[float] = []
    filled = from_documents = 0
    for row in rows:
        counts = breakdown.setdefault(row.process_type, [0, 0, 0])
        by_status[row.status.value] = by_status.get(row.status.value, 0) + 1
        if row.status == CaseStatus.SIGNED:
            counts[2] += 1
            if row.signed_at is not None and row.created_at is not None:
                hours.append(max((row.signed_at - row.created_at).total_seconds(), 0.0) / 3600)
        elif row.pipeline_stage == _WAITING_STAGE or row.id in linked:
            counts[1] += 1
        else:
            counts[0] += 1
        for key, value in row.field_values.items():
            if not str(value or "").strip():
                continue
            filled += 1
            source = row.field_sources.get(key)
            if isinstance(source, dict) and source.get("source") == "document":
                from_documents += 1
    totals = [sum(item[index] for item in breakdown.values()) for index in range(3)]
    return AnalyticsSummary(
        total_cases=len(rows),
        filling_cases=totals[0],
        waiting_for_signature_cases=totals[1],
        signed_cases=totals[2],
        avg_hours_to_sign=round(sum(hours) / len(hours), 2) if hours else None,
        auto_extraction_rate_pct=round(100 * from_documents / filled, 1) if filled else 0.0,
        by_process_type=[
            ProcessBreakdown(
                process_type=key,
                total=sum(counts),
                filling=counts[0],
                waiting_for_signature=counts[1],
                signed=counts[2],
            )
            for key, counts in sorted(breakdown.items())
        ],
        by_status=dict(sorted(by_status.items())),
    )


def _cell(value: str | None) -> str:
    text = value or ""
    return f"'{text}" if text.startswith(_FORMULA_LEAD) else text


async def export_csv(session: AsyncSession, scope: CaseScope) -> bytes:
    """Every case of the office, newest first, as UTF-8 with a BOM so Excel reads the Hebrew."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in await _rows(session, scope):
        signed = row.status == CaseStatus.SIGNED
        writer.writerow(
            [
                str(row.id),
                _cell(row.client_name),
                row.process_type,
                row.status.value,
                row.created_at.isoformat() if row.created_at else "",
                row.signed_at.isoformat() if signed and row.signed_at else "",
                (row.verification_id or "") if signed else "",
            ]
        )
    return buffer.getvalue().encode("utf-8-sig")
