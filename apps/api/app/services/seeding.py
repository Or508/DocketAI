from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.processes import PROCESSES
from app.models.process_definition import ProcessDefinition


async def seed_processes(session: AsyncSession) -> None:
    for spec in PROCESSES:
        existing = await session.scalar(
            select(ProcessDefinition).where(ProcessDefinition.key == spec.key)
        )
        if existing is not None:
            continue
        session.add(
            ProcessDefinition(
                key=spec.key,
                name=spec.name,
                description=spec.description,
                required_documents=spec.required_documents,
                optional_documents=spec.optional_documents,
                required_fields=spec.required_fields,
                template_filename=spec.template_filename,
                layout=spec.layout,
            )
        )
    await session.commit()
