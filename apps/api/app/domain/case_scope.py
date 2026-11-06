import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.models.case import Case


@dataclass(frozen=True)
class CaseScope:
    organization_id: uuid.UUID | None
    actor: str

    @classmethod
    def office(cls, organization_id: uuid.UUID, user_id: uuid.UUID) -> "CaseScope":
        return cls(organization_id=organization_id, actor=f"user:{user_id}")

    @classmethod
    def system(cls) -> "CaseScope":
        return cls(organization_id=None, actor="system")


def case_query(scope: CaseScope):
    stmt = select(Case)
    if scope.organization_id is not None:
        stmt = stmt.where(Case.organization_id == scope.organization_id)
    return stmt
