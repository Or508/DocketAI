"""The office's audit trail across every case it owns. Everything is read through the caller's case scope."""

import csv
import io

from sqlalchemy import Select, String, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.domain.archive import timeline_metadata
from app.domain.case_scope import CaseScope, case_query
from app.domain.enums import AuditAction
from app.domain.signing_links import as_utc
from app.core.time import utcnow
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.process_definition import ProcessDefinition
from app.schemas.audit import AuditCenter, AuditEvent

MAX_LIMIT = 500
# The export is the whole filtered trail, not one screen of it. This bounds a single file.
EXPORT_LIMIT = 50_000
CSV_COLUMNS = ("event_id", "created_at", "case_id", "client_name", "process_type", "action", "actor")


def _like(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _owned(scope: CaseScope) -> Select:
    # Every row is reached through the caller's own cases, so another office's events never appear.
    return case_query(scope).join(AuditLog, AuditLog.case_id == Case.id)


def _filtered(scope: CaseScope, action: str | None, q: str | None) -> Select:
    """The office's events narrowed by one action and a search term. Shared by the screen and the export."""
    chosen: AuditAction | None = None
    if action and action.strip():
        try:
            chosen = AuditAction(action.strip())
        except ValueError as exc:
            raise BadRequestError("Unknown audit action.") from exc
    filtered = _owned(scope).join(ProcessDefinition, ProcessDefinition.id == Case.process_definition_id)
    if chosen is not None:
        filtered = filtered.where(AuditLog.action == chosen)
    term = (q or "").strip()
    if term:
        pattern = _like(term)
        clauses = [
            Case.client_name.ilike(pattern, escape="\\"),
            Case.name.ilike(pattern, escape="\\"),
            AuditLog.actor.ilike(pattern, escape="\\"),
            ProcessDefinition.key.ilike(pattern, escape="\\"),
            cast(Case.case_reference, String).ilike(pattern, escape="\\"),
        ]
        named = [item for item in AuditAction if term.lower() in item.value]
        if named:
            clauses.append(AuditLog.action.in_(named))
        filtered = filtered.where(or_(*clauses))
    return filtered


def _cell(value: object) -> str:
    """A spreadsheet must show this as text, never run it as a formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


async def export_csv(
    session: AsyncSession,
    scope: CaseScope,
    *,
    action: str | None = None,
    q: str | None = None,
) -> bytes:
    """The filtered audit trail, newest first, as UTF-8 with a BOM so Excel reads the Hebrew.

    Only who did what, when, on which case. No event metadata, so no value from a document.
    """
    rows = (
        await session.execute(
            _filtered(scope, action, q)
            .with_only_columns(
                AuditLog.id,
                AuditLog.created_at,
                AuditLog.case_id,
                Case.client_name,
                ProcessDefinition.key,
                AuditLog.action,
                AuditLog.actor,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(EXPORT_LIMIT)
        )
    ).all()
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for event_id, created_at, case_id, client_name, process_type, event_action, actor in rows:
        stamp = as_utc(created_at)
        writer.writerow(
            [
                str(event_id),
                stamp.isoformat() if stamp else "",
                str(case_id),
                _cell(client_name),
                _cell(process_type),
                AuditAction(event_action).value,
                _cell(actor),
            ]
        )
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


async def audit_center(
    session: AsyncSession,
    scope: CaseScope,
    *,
    action: str | None = None,
    q: str | None = None,
    limit: int = 100,
) -> AuditCenter:
    limit = max(1, min(limit, MAX_LIMIT))
    counted = _owned(scope).with_only_columns(AuditLog.action, func.count()).group_by(AuditLog.action)
    counts = {AuditAction(item).value: int(total) for item, total in (await session.execute(counted)).all()}
    filtered = _filtered(scope, action, q)

    matched = int((await session.execute(filtered.with_only_columns(func.count()))).scalar_one())
    rows = (
        await session.execute(
            filtered.with_only_columns(
                AuditLog.id,
                AuditLog.case_id,
                Case.client_name,
                Case.name,
                ProcessDefinition.key,
                AuditLog.action,
                AuditLog.actor,
                AuditLog.created_at,
                AuditLog.previous_value,
                AuditLog.new_value,
            )
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
    ).all()

    return AuditCenter(
        total_events=sum(counts.values()),
        signed_count=counts.get(AuditAction.FILL_AND_SIGN.value, 0),
        smart_uploads_count=counts.get(AuditAction.SMART_UPLOAD_COMPLETED.value, 0),
        vault_reuses_count=counts.get(AuditAction.CLIENT_VAULT_REUSED.value, 0),
        revocations_count=counts.get(AuditAction.SIGNING_LINK_REVOKED.value, 0),
        action_counts=dict(sorted(counts.items())),
        matched_events=matched,
        events=[
            AuditEvent(
                event_id=event_id,
                case_id=case_id,
                client_name=client_name,
                case_name=case_name,
                process_type=process_type,
                action=AuditAction(event_action).value,
                actor=actor,
                created_at=as_utc(created_at) or utcnow(),
                metadata=timeline_metadata(previous_value, new_value),
            )
            for (
                event_id,
                case_id,
                client_name,
                case_name,
                process_type,
                event_action,
                actor,
                created_at,
                previous_value,
                new_value,
            ) in rows
        ],
    )
