import argparse
import asyncio
import getpass
import os
import sys

from sqlalchemy import select, update

from app.core.config import get_settings
from app.db.session import session_scope
from app.models.organization import Organization
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth_service import hash_password
from app.services.storage_migration import migrate_storage
from app.core.time import utcnow


def _password() -> str:
    supplied = os.environ.get("DOCKET_USER_PASSWORD")
    if supplied is not None and supplied != "":
        password = supplied
    else:
        password = getpass.getpass("Password: ")
    if len(password) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        raise SystemExit(1)
    return password


async def _create_user(organization: str, email: str, display_name: str, password: str) -> None:
    normalized = email.strip().lower()
    async with session_scope() as session:
        org = await session.scalar(select(Organization).where(Organization.name == organization))
        if org is None:
            org = Organization(name=organization)
            session.add(org)
            await session.flush()
        existing = await session.scalar(select(User).where(User.email == normalized))
        if existing is not None:
            print("A user with that email already exists.", file=sys.stderr)
            raise SystemExit(1)
        session.add(
            User(
                organization_id=org.id,
                email=normalized,
                password_hash=hash_password(password),
                display_name=display_name,
            )
        )
        await session.commit()
    print(f"Created {normalized} in {organization}.")


async def _set_password(email: str, password: str) -> None:
    normalized = email.strip().lower()
    async with session_scope() as session:
        user = await session.scalar(select(User).where(User.email == normalized))
        if user is None:
            print("No user with that email.", file=sys.stderr)
            raise SystemExit(1)
        user.password_hash = hash_password(password)
        user.failed_logins = 0
        user.locked_until = None
        await session.execute(
            update(UserSession)
            .where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
        await session.commit()
    print(f"Password updated for {normalized}.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-user")
    create.add_argument("--organization", required=True)
    create.add_argument("--email", required=True)
    create.add_argument("--display-name", required=True)
    reset = commands.add_parser("set-password")
    reset.add_argument("--email", required=True)
    migrate = commands.add_parser("migrate-storage")
    migrate.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.command == "migrate-storage":
        raise SystemExit(asyncio.run(migrate_storage(dry_run=args.dry_run)))
    get_settings()
    password = _password()
    if args.command == "create-user":
        asyncio.run(_create_user(args.organization, args.email, args.display_name, password))
    else:
        asyncio.run(_set_password(args.email, password))


if __name__ == "__main__":
    main()
