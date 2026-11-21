import re
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import current_user, require_owner
from app.core.exceptions import BadRequestError, ForbiddenError
from app.db.session import get_session
from app.domain.professions import PROFESSIONS, profession as profession_of
from app.models.organization import Organization
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/organization", tags=["organization"])


class ProfessionOption(BaseModel):
    key: str
    label_he: str
    client_term_he: str
    case_term_he: str


class OrganizationRead(BaseModel):
    name: str
    # Shown to clients on the signing and upload pages, so they know how to reach the office.
    contact_phone: str | None
    contact_email: str | None
    profession: ProfessionOption
    # Off: no document, page, or chat message of this office is sent to an AI model.
    ai_reading_enabled: bool
    # Every profession an office can choose, for the onboarding and settings screens.
    professions: list[ProfessionOption]


class ProfessionChange(BaseModel):
    profession: str = Field(max_length=40)


class ContactChange(BaseModel):
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=320)


class AiReadingChange(BaseModel):
    enabled: bool


def _option(key: str) -> ProfessionOption:
    kind = profession_of(key)
    return ProfessionOption(key=kind.key, label_he=kind.label_he, client_term_he=kind.client_he, case_term_he=kind.case_he)


def _read(organization: Organization) -> OrganizationRead:
    return OrganizationRead(
        name=organization.name,
        contact_phone=organization.contact_phone,
        contact_email=organization.contact_email,
        profession=_option(organization.profession),
        ai_reading_enabled=bool(organization.ai_reading_enabled),
        professions=[_option(key) for key in PROFESSIONS],
    )


@router.get("", response_model=OrganizationRead)
async def read_organization(
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead:
    organization = await session.get(Organization, user.organization_id)
    assert organization is not None
    return _read(organization)


@router.put("/profession", response_model=OrganizationRead)
async def change_profession(
    payload: ProfessionChange,
    user: User = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead:
    """Set what kind of office this is. Existing cases keep their processes."""
    if payload.profession not in PROFESSIONS:
        raise BadRequestError("Unknown profession.")
    organization = await session.get(Organization, user.organization_id)
    assert organization is not None
    if organization.profession != payload.profession:
        previous = organization.profession
        organization.profession = payload.profession
        await session.commit()
        # The audit trail is per case; an office-wide change is recorded in the server log.
        logger.info("Organization %s changed profession from %s to %s (user %s)", organization.id, previous, payload.profession, user.id)
    return _read(organization)


@router.put("/ai-reading", response_model=OrganizationRead)
async def change_ai_reading(
    payload: AiReadingChange,
    user: User = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead:
    """Turn AI reading on or off for the whole office. Documents read before keep what was read."""
    organization = await session.get(Organization, user.organization_id)
    assert organization is not None
    if payload.enabled and organization.demo_expires_at is not None:
        # A public demo must cost nothing and send no one's text to an AI provider.
        raise ForbiddenError("בדמו הקריאה האוטומטית כבויה, כדי שלא יישלח מידע לספק AI.")
    if bool(organization.ai_reading_enabled) != payload.enabled:
        organization.ai_reading_enabled = payload.enabled
        await session.commit()
        logger.info("Organization %s turned AI reading %s (user %s)", organization.id, "on" if payload.enabled else "off", user.id)
    return _read(organization)


_PHONE = re.compile(r"^\+?[0-9][0-9 \-]{7,18}[0-9]$")


@router.put("/contact", response_model=OrganizationRead)
async def change_contact(
    payload: ContactChange,
    user: User = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
) -> OrganizationRead:
    """The phone and email clients see on their signing and upload pages. Blank removes one."""
    phone = (payload.phone or "").strip() or None
    email = (payload.email or "").strip().lower() or None
    if phone is not None and (not _PHONE.match(phone) or not 9 <= sum(ch.isdigit() for ch in phone) <= 15):
        raise BadRequestError("מספר הטלפון לא תקין. כתבו ספרות בלבד, למשל 03-1234567.", code="bad_phone")
    if email is not None and ("@" not in email or "." not in email.partition("@")[2] or " " in email):
        raise BadRequestError("כתובת האימייל לא תקינה.", code="bad_email")
    organization = await session.get(Organization, user.organization_id)
    assert organization is not None
    organization.contact_phone = phone
    organization.contact_email = email
    await session.commit()
    return _read(organization)
