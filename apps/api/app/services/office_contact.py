import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.schemas.portal import OfficeContact


async def office_contact(session: AsyncSession, organization_id: uuid.UUID | None) -> OfficeContact | None:
    """The office a client's link belongs to, as the client may see it."""
    if organization_id is None:
        return None
    organization = await session.get(Organization, organization_id)
    if organization is None:
        return None
    return OfficeContact(
        name=organization.name,
        phone=organization.contact_phone or None,
        email=organization.contact_email or None,
    )
