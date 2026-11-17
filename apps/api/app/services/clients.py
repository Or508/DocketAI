"""The office's client book: every case gathered under the person it is about.

A client is the ID number their cases hold. A case with no ID number yet is filed by
its client name, and joins an ID-numbered client when exactly one carries that name.
Everything is read through the caller's case scope.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.case_scope import CaseScope, case_query
from app.domain.enums import CaseStatus, ClassificationSource, DocumentStatus
from app.domain.signing_links import as_utc
from app.models.case import Case
from app.models.document import Document
from app.schemas.clients import ClientCase, ClientRead

# The documents a person hands over once and every later case can reuse.
VAULT_TYPES = ("id_copy", "proof_of_address", "bank_confirmation")
# Details about the person, as opposed to details about one case. Only these travel to a new case.
PERSONAL_KEYS = (
    "national_id",
    "first_name",
    "last_name",
    "full_name",
    "phone",
    "email",
    "street",
    "house_number",
    "city",
    "address_he",
    "bank_name",
    "bank_branch",
    "bank_account",
)
_ID_KEYS = ("national_id", "id_number")
_SPACE = re.compile(r"\s+")


def _values(case: Case) -> dict[str, str]:
    return {str(key): str(value).strip() for key, value in (case.field_values or {}).items() if str(value).strip()}


def _id_number(case: Case) -> str | None:
    values = _values(case)
    return next((values[key] for key in _ID_KEYS if values.get(key)), None)


def _name_key(name: str | None) -> str:
    return _SPACE.sub(" ", (name or "").strip()).casefold()


def _newest_first(cases: list[Case]) -> list[Case]:
    return sorted(cases, key=lambda item: (as_utc(item.created_at) or as_utc(item.updated_at), str(item.id)), reverse=True)


@dataclass
class Client:
    key: str
    id_number: str | None
    # Newest first.
    cases: list[Case] = field(default_factory=list)

    def profile(self) -> dict[str, str]:
        """The latest known value of every personal detail, with the obvious ones derived."""
        known: dict[str, str] = {}
        for case in self.cases:
            values = _values(case)
            for key in PERSONAL_KEYS:
                if key not in known and values.get(key):
                    known[key] = values[key]
        if self.id_number:
            known["national_id"] = self.id_number
        if "full_name" not in known and known.get("first_name") and known.get("last_name"):
            known["full_name"] = f"{known['first_name']} {known['last_name']}"
        if "full_name" in known and not (known.get("first_name") or known.get("last_name")):
            parts = known["full_name"].split()
            # A name of exactly two words splits without guessing.
            if len(parts) == 2:
                known["first_name"], known["last_name"] = parts
        if "address_he" not in known and known.get("street") and known.get("city"):
            street = " ".join(item for item in (known["street"], known.get("house_number", "")) if item)
            known["address_he"] = f"{street}, {known['city']}"
        return known

    def name(self) -> str:
        named = next((case.client_name.strip() for case in self.cases if (case.client_name or "").strip()), None)
        return named or self.profile().get("full_name") or self.cases[0].name

    def vault(self, first: Case | None = None) -> dict[str, Document]:
        """The newest filed document of each vault type, looking in `first` before the other cases."""
        ordered = self.cases if first is None else [first, *[case for case in self.cases if case.id != first.id]]
        found: dict[str, Document] = {}
        for case in ordered:
            documents = sorted(case.documents, key=lambda item: (item.created_at, str(item.id)), reverse=True)
            for document in documents:
                if document.document_type in VAULT_TYPES and document.document_type not in found and _filed(document):
                    found[document.document_type] = document
        return {key: found[key] for key in VAULT_TYPES if key in found}


def _filed(document: Document) -> bool:
    """A document that sits in its drawer: read and labelled, or labelled by the office."""
    if document.role != "evidence" or document.status == DocumentStatus.FAILED:
        return False
    return document.status == DocumentStatus.CLASSIFIED or document.classification_source == ClassificationSource.HUMAN


def group_clients(cases: list[Case]) -> list[Client]:
    """Gather cases into clients. A case with neither an ID number nor a client name is left out."""
    by_id: dict[str, Client] = {}
    by_name: dict[str, Client] = {}
    for case in _newest_first(cases):
        number = _id_number(case)
        if number:
            by_id.setdefault(number, Client(key=f"id:{number}", id_number=number)).cases.append(case)
            continue
        name = _name_key(case.client_name)
        if name:
            by_name.setdefault(name, Client(key=f"name:{name}", id_number=None)).cases.append(case)

    # A name-only case belongs to the one ID-numbered client of that name. Two such clients: it stays apart.
    names: dict[str, list[Client]] = {}
    for client in by_id.values():
        for name in {_name_key(case.client_name) for case in client.cases} - {""}:
            names.setdefault(name, []).append(client)
    clients = list(by_id.values())
    for name, client in by_name.items():
        owners = names.get(name, [])
        if len(owners) == 1:
            owners[0].cases = _newest_first(owners[0].cases + client.cases)
        else:
            clients.append(client)
    clients.sort(
        key=lambda item: (as_utc(item.cases[0].created_at) or as_utc(item.cases[0].updated_at), item.key),
        reverse=True,
    )
    return clients


async def load_cases(session: AsyncSession, scope: CaseScope) -> list[Case]:
    stmt = case_query(scope).options(selectinload(Case.documents), selectinload(Case.process_definition))
    return list((await session.scalars(stmt)).all())


def _bank_summary(profile: dict[str, str]) -> str | None:
    parts: list[str] = []
    if profile.get("bank_name"):
        parts.append(profile["bank_name"])
    if profile.get("bank_branch"):
        parts.append(f"סניף {profile['bank_branch']}")
    account = profile.get("bank_account", "")
    if account:
        parts.append(f"חשבון ••{account[-4:]}" if len(account) > 4 else f"חשבון {account}")
    return " · ".join(parts) or None


def _address_summary(profile: dict[str, str]) -> str | None:
    if profile.get("street") and profile.get("city"):
        street = " ".join(item for item in (profile["street"], profile.get("house_number", "")) if item)
        return f"{street}, {profile['city']}"
    return profile.get("address_he") or profile.get("city") or None


def client_read(client: Client) -> ClientRead:
    profile = client.profile()
    vault = client.vault()
    return ClientRead(
        client_key=client.key,
        client_name=client.name(),
        id_number=client.id_number,
        phone=profile.get("phone"),
        address_summary=_address_summary(profile),
        bank_summary=_bank_summary(profile),
        total_cases=len(client.cases),
        signed_cases=sum(1 for case in client.cases if case.status == CaseStatus.SIGNED),
        reusable_docs_count=len(vault),
        reusable_doc_types=[key for key in VAULT_TYPES if key in vault],
        latest_case_id=client.cases[0].id,
        cases=[
            ClientCase(
                case_id=case.id,
                process_type=case.process_definition.key,
                status=case.status,
                created_at=as_utc(case.created_at),
                signed_at=as_utc(case.signed_at),
                verification_id=case.signer_verification_id if case.status == CaseStatus.SIGNED else None,
            )
            for case in client.cases
        ],
    )


async def list_clients(session: AsyncSession, scope: CaseScope) -> list[ClientRead]:
    return [client_read(client) for client in group_clients(await load_cases(session, scope))]
