import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.exceptions import UnauthorizedError
from app.core.time import utcnow
from app.models.user import User
from app.models.user_session import UserSession

_HASHER = PasswordHasher()
_DUMMY_HASH = _HASHER.hash("docketai-dummy-password")
_LOGIN_ERROR = "Email or password is incorrect."


def hash_password(password: str) -> str:
    return _HASHER.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _HASHER.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def login(self, email: str, password: str) -> tuple[str, datetime, User]:
        normalized = email.strip().lower()
        user = await self.session.scalar(select(User).where(User.email == normalized))
        if user is None:
            verify_password(password, _DUMMY_HASH)
            raise UnauthorizedError(_LOGIN_ERROR)
        password_ok = verify_password(password, user.password_hash)
        locked_until = user.locked_until
        if locked_until is not None and locked_until.tzinfo is None:
            from datetime import timezone

            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until is not None and locked_until > utcnow():
            raise UnauthorizedError(_LOGIN_ERROR)
        if not password_ok:
            user.failed_logins = int(user.failed_logins or 0) + 1
            if user.failed_logins >= self.settings.login_max_failures:
                user.locked_until = utcnow() + timedelta(minutes=self.settings.login_lock_minutes)
            await self.session.commit()
            raise UnauthorizedError(_LOGIN_ERROR)
        if not user.is_active:
            raise UnauthorizedError(_LOGIN_ERROR)
        user.failed_logins = 0
        user.locked_until = None
        token = secrets.token_urlsafe(32)
        record = UserSession(
            user_id=user.id,
            token_hash=_token_hash(token),
            created_at=utcnow(),
            expires_at=utcnow() + timedelta(hours=self.settings.session_ttl_hours),
        )
        self.session.add(record)
        await self.session.commit()
        return token, record.expires_at, user

    async def resolve_session(self, token: str) -> User:
        record = await self.session.scalar(
            select(UserSession).where(UserSession.token_hash == _token_hash(token))
        )
        if record is None or record.revoked_at is not None:
            raise UnauthorizedError()
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            from datetime import timezone

            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= utcnow():
            raise UnauthorizedError()
        user = await self.session.get(User, record.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError()
        return user

    async def logout(self, token: str) -> None:
        record = await self.session.scalar(
            select(UserSession).where(UserSession.token_hash == _token_hash(token))
        )
        if record is None or record.revoked_at is not None:
            return
        record.revoked_at = utcnow()
        await self.session.commit()
