"""A visitor's private sandbox office: no email, no password, gone when the clock runs out."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from starlette.datastructures import Headers, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.container import Container
from app.core.time import utcnow
from app.domain.case_scope import CaseScope, case_query
from app.domain.enums import CaseStatus
from app.models.account_token import AccountToken
from app.models.organization import Organization
from app.models.outreach import CaseOutreach, OutboundMessage
from app.models.user import User
from app.models.user_session import UserSession
from app.schemas.case import CaseCreate
from app.services.auth_service import AuthService, hash_password
from app.services.case_service import CaseService

logger = logging.getLogger(__name__)

_ASSETS = Path(__file__).resolve().parents[1] / "assets" / "demo"

# Synthetic people only. The PDFs beside this service come from scripts/demo_documents.py (`--api`), and all of them
# belong to one invented person, דנה כהן. So her case is the one that is ready for a signer; the others start empty and
# show the "missing documents" state, which the visitor can fill by sending the client a link.
_SAMPLE_CLIENT = "דנה כהן"

# Which drawer each sample belongs in. A sample whose type a process does not ask for is skipped.
_FILE_TYPES = {
    "01-teudat-zehut.pdf": "id_copy",
    "02-arnona.pdf": "proof_of_address",
    "03-ishur-bank.pdf": "bank_confirmation",
    "04-hozeh-mecher.pdf": "purchase_agreement",
    "05-nesach-tabu.pdf": "title_deed",
    "06-ishur-misim.pdf": "tax_clearance",
}

# What the office itself types into a ready case. The client's own phone is left for the signer to add.
_OFFICE_VALUES: dict[str, dict[str, str]] = {
    "real_estate": {
        "buyer_name": "דנה כהן",
        "seller_name": "יוסף מזרחי",
        "property_address_he": "רחוב הנביאים 40, ירושלים",
        "parcel_number": "גוש 30040 חלקה 112",
        "price": "2,450,000",
        "contract_date": "15/12/2026",
    },
    "dental_treatment_plan": {
        "treatment_plan": "שתלים בשיניים 36 ו-46, כתר חרסינה על שן 21",
        "total_price": "18,500",
        "payment_terms": "12 תשלומים שווים בכרטיס אשראי",
        "treating_doctor": "ד״ר מיכל שגיא",
        "plan_date": "21/11/2026",
    },
    "dental_botox_consent": {
        "treatment_area": "מצח וקמטי צחוק",
        "product_name": "Botox",
        "units": "30",
        "treating_doctor": "ד״ר מיכל שגיא",
        "treatment_date": "28/11/2026",
    },
}

# (profession, office name, cases); each case is (case name, client, process, ready for a signer).
_SCENARIOS: dict[str, tuple[str, str, tuple[tuple[str, str, str, bool], ...]]] = {
    "law": (
        "law",
        "משרד הדגמה",
        (
            ("עסקת מקרקעין — דנה כהן", _SAMPLE_CLIENT, "real_estate", True),
            ("עסקת מקרקעין — יונתן מזרחי", "יונתן מזרחי", "real_estate", False),
            ("קליטת עובד — מאיה אברהם", "מאיה אברהם", "employee_onboarding", False),
        ),
    ),
    "dental": (
        "dental_clinic",
        "מרפאת הדגמה",
        (
            ("תכנית טיפול — דנה כהן", _SAMPLE_CLIENT, "dental_treatment_plan", True),
            ("הסכמה לטיפול — יונתן מזרחי", "יונתן מזרחי", "dental_botox_consent", False),
        ),
    ),
    "hr": (
        "accounting",
        "משאבי אנוש — הדגמה",
        (
            ("טופס 101 — דנה כהן", _SAMPLE_CLIENT, "employee_onboarding", True),
            ("טופס 101 — יונתן מזרחי", "יונתן מזרחי", "employee_onboarding", False),
            ("טופס 101 — מאיה אברהם", "מאיה אברהם", "employee_onboarding", False),
        ),
    ),
}


def local_phone(international: str) -> str:
    """972547302757 → 054-7302757: the way an Israeli reads and dials it. WhatsApp links keep the international form."""
    digits = "".join(ch for ch in international if ch.isdigit())
    if digits.startswith("972") and len(digits) >= 11:
        digits = "0" + digits[3:]
    return f"{digits[:3]}-{digits[3:]}" if len(digits) == 10 and digits.startswith("05") else digits


class DemoService:
    def __init__(self, session: AsyncSession, settings: Settings, container: Container) -> None:
        self.session = session
        self.settings = settings
        self.container = container

    async def start(self, scenario: str) -> tuple[str, object, User]:
        profession, office_name, cases = _SCENARIOS[scenario]
        organization = Organization(
            name=office_name,
            profession=profession,
            ai_reading_enabled=False,
            contact_phone=local_phone(self.settings.demo_whatsapp),
            demo_expires_at=utcnow() + timedelta(hours=self.settings.demo_ttl_hours),
        )
        self.session.add(organization)
        await self.session.flush()
        user = User(
            organization_id=organization.id,
            email=f"demo-{uuid.uuid4().hex}@demo.invalid",
            password_hash=hash_password(secrets.token_urlsafe(32)),
            display_name="משרד הדמו",
            role="owner",
        )
        self.session.add(user)
        await self.session.commit()
        user_id = user.id
        await self._seed(organization.id, user_id, cases)
        # Uploading a sample can roll the session back, which drops the user from memory.
        user = await self.session.get(User, user_id)
        assert user is not None
        token, expires_at = await AuthService(self.session, self.settings).issue_session(user)
        return token, expires_at, user

    async def _seed(
        self,
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        cases: tuple[tuple[str, str, str, bool], ...],
    ) -> None:
        for name, client, process_key, ready in cases:
            # A fresh service per case: a refused sample rolls the session back, and nothing stale may carry over.
            service = CaseService(self.session, self.container, CaseScope.office(organization_id, user_id))
            created = await service.create_case(CaseCreate(name=name, process_key=process_key, client_name=client))
            if ready:
                try:
                    await self._fill(service, created.id, process_key)
                except Exception:
                    logger.exception("Demo case %s was left part-filled", created.id)

    async def _fill(self, service: CaseService, case_id: uuid.UUID, process_key: str) -> None:
        from app.core.exceptions import BadRequestError
        from app.schemas.chat import FieldUpdateRequest
        from app.workers.runner import process_case_job

        uploaded = False
        for path in sorted(_ASSETS.glob("*.pdf")):
            document_type = _FILE_TYPES.get(path.name)
            if document_type is None:
                continue
            upload = UploadFile(
                BytesIO(path.read_bytes()),
                filename=path.name,
                headers=Headers({"content-type": "application/pdf"}),
            )
            try:
                await service.add_uploads(case_id, [upload], document_type)
                uploaded = True
            except BadRequestError:
                # This process has no drawer for that sample.
                await self.session.rollback()
        if uploaded:
            # Read now, even where a queue exists, so the office's details below never race the reader.
            await process_case_job(case_id, self.container)
        for key, value in _OFFICE_VALUES.get(process_key, {}).items():
            await service.set_field(case_id, FieldUpdateRequest(key=key, value=value))


async def delete_expired_demos(container: Container) -> int:
    """Delete demo offices whose time is up. A real office has no expiry, so it is never selected."""
    from app.db.session import session_scope

    async with session_scope() as session:
        expired = list(
            await session.scalars(
                select(Organization.id).where(
                    Organization.demo_expires_at.is_not(None),
                    Organization.demo_expires_at < utcnow(),
                )
            )
        )
    removed = 0
    for org_id in expired:
        try:
            await _delete_demo(container, org_id)
            removed += 1
        except Exception:
            logger.exception("Could not delete demo office %s", org_id)
    if removed:
        logger.info("Deleted %s expired demo offices", removed)
    return removed


async def _delete_demo(container: Container, org_id: uuid.UUID) -> None:
    from app.db.session import session_scope

    async with session_scope() as session:
        owner = await session.scalar(select(User).where(User.organization_id == org_id).order_by(User.created_at))
        if owner is not None:
            scope = CaseScope.office(org_id, owner.id)
            service = CaseService(session, container, scope)
            for case in list(await session.scalars(case_query(scope))):
                await session.execute(delete(OutboundMessage).where(OutboundMessage.case_id == case.id))
                await session.execute(delete(CaseOutreach).where(CaseOutreach.case_id == case.id))
                await session.commit()
                if case.status == CaseStatus.SIGNED:
                    await service.reopen(case.id)
                await service.delete_case(case.id)
        user_ids = list(await session.scalars(select(User.id).where(User.organization_id == org_id)))
        if user_ids:
            await session.execute(delete(UserSession).where(UserSession.user_id.in_(user_ids)))
            await session.execute(delete(AccountToken).where(AccountToken.user_id.in_(user_ids)))
            await session.execute(delete(User).where(User.id.in_(user_ids)))
        await session.execute(delete(Organization).where(Organization.id == org_id))
        await session.commit()
