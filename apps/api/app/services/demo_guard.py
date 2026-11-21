"""A public demo office may hand a client a WhatsApp link, and may not send email."""

from app.core.exceptions import ForbiddenError
from app.models.organization import Organization

DEMO_EMAIL_DETAIL = "בדמו אפשר לשלוח רק בוואטסאפ, כדי שלא יישלחו מיילים לאנשים אמיתיים."


def is_demo(organization: Organization | None) -> bool:
    return organization is not None and organization.demo_expires_at is not None


def refuse_demo_email(organization: Organization | None) -> None:
    if is_demo(organization):
        raise ForbiddenError(DEMO_EMAIL_DETAIL)
