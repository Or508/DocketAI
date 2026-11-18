from fastapi import APIRouter, Depends, Query
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.db.session import get_session
from app.domain.professions import PROFESSIONS, professions_of
from app.models.process_definition import ProcessDefinition
from app.schemas.process import DocumentTypeSpec, FieldSpec, ProcessRead

router = APIRouter(prefix="/processes", tags=["processes"])

_documents = TypeAdapter(list[DocumentTypeSpec])
_fields = TypeAdapter(list[FieldSpec])


@router.get("", response_model=list[ProcessRead])
async def list_processes(
    profession: str | None = Query(default=None, max_length=40),
    session: AsyncSession = Depends(get_session),
) -> list[ProcessRead]:
    """Every process, or only those one profession uses (`?profession=dental_clinic`)."""
    if profession is not None and profession not in PROFESSIONS:
        raise BadRequestError("Unknown profession.")
    rows = (await session.scalars(select(ProcessDefinition).order_by(ProcessDefinition.name))).all()
    return [
        ProcessRead(
            key=row.key,
            name=row.name,
            description=row.description,
            required_documents=_documents.validate_python(row.required_documents or []),
            optional_documents=_documents.validate_python(row.optional_documents or []),
            required_fields=_fields.validate_python(row.required_fields or []),
            professions=list(professions_of(row.key)),
        )
        for row in rows
        if profession is None or profession in professions_of(row.key)
    ]
