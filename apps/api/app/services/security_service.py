"""A signed-in staff member's own security: password change and two-step login.

The authenticator secret is stored encrypted (Fernet). The key comes from MFA_SECRET_KEY, or,
when that is unset, from a key file this server creates once beside its database. Recovery codes
are stored only as hashes and shown once.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError
from app.core.time import utcnow
from app.domain import totp
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth_service import _token_hash, hash_password, verify_password

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 12
RECOVERY_CODE_COUNT = 8
_WRONG_PASSWORD = "The current password is incorrect."
_WRONG_CODE = "The code is incorrect or has expired."


def _fernet(settings: Settings) -> Fernet:
    if settings.mfa_secret_key:
        return Fernet(settings.mfa_secret_key.encode("ascii"))
    path: Path = settings.resolved_mfa_key_path
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        staged.write_bytes(Fernet.generate_key())
        os.replace(staged, path)
        logger.warning("Created the two-step login key at %s. Back it up with the database.", path)
    return Fernet(path.read_bytes().strip())


def seal_secret(settings: Settings, secret: str) -> str:
    return _fernet(settings).encrypt(secret.encode("ascii")).decode("ascii")


def open_secret(settings: Settings, sealed: str) -> str:
    try:
        return _fernet(settings).decrypt(sealed.encode("ascii")).decode("ascii")
    except InvalidToken as exc:
        raise RuntimeError("The two-step login key does not match the stored secret.") from exc


def _recovery_hash(code: str) -> str:
    return hashlib.sha256("".join(code.lower().split()).encode()).hexdigest()


def new_recovery_codes() -> tuple[list[str], list[str]]:
    """Codes to show once (xxxx-xxxx), and the hashes to keep."""
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = secrets.token_hex(4)
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes, [_recovery_hash(code) for code in codes]


def check_second_factor(settings: Settings, user: User, code: str) -> bool:
    """True for a fresh authenticator code or an unused recovery code; either is then spent."""
    if not user.mfa_enabled or not user.mfa_secret:
        return False
    step = totp.verify(open_secret(settings, user.mfa_secret), code, last_step=user.mfa_last_step)
    if step is not None:
        user.mfa_last_step = step
        return True
    wanted = _recovery_hash(code)
    remaining = list(user.mfa_recovery_hashes or [])
    for index, stored in enumerate(remaining):
        if hmac.compare_digest(stored, wanted):
            del remaining[index]
            user.mfa_recovery_hashes = remaining
            return True
    return False


class SecurityService:
    def __init__(self, session: AsyncSession, settings: Settings, user: User) -> None:
        self.session = session
        self.settings = settings
        self.user = user

    def status(self) -> dict:
        return {
            "mfa_enabled": bool(self.user.mfa_enabled),
            "recovery_codes_left": len(self.user.mfa_recovery_hashes or []) if self.user.mfa_enabled else 0,
            "min_password_length": MIN_PASSWORD_LENGTH,
        }

    async def _require_password(self, password: str) -> None:
        # 400, not 401: the session is fine, only the typed password is wrong. A 401 would sign the user out.
        if not await asyncio.to_thread(verify_password, password, self.user.password_hash):
            raise BadRequestError(_WRONG_PASSWORD, code="wrong_password")

    async def change_password(self, current: str, new: str, keep_token: str) -> None:
        """Set a new password. Every other session of this user is signed out; this one stays."""
        await self._require_password(current)
        if len(new) < MIN_PASSWORD_LENGTH:
            raise BadRequestError(f"Choose a password of at least {MIN_PASSWORD_LENGTH} characters.", code="weak_password")
        if await asyncio.to_thread(verify_password, new, self.user.password_hash):
            raise BadRequestError("The new password must differ from the current one.", code="same_password")
        self.user.password_hash = await asyncio.to_thread(hash_password, new)
        await self.session.execute(
            update(UserSession)
            .where(
                UserSession.user_id == self.user.id,
                UserSession.revoked_at.is_(None),
                UserSession.token_hash != _token_hash(keep_token),
            )
            .values(revoked_at=utcnow())
        )
        await self.session.commit()

    async def start_mfa(self) -> dict:
        """A new secret to scan. It counts only once a code from the app confirms it."""
        if self.user.mfa_enabled:
            raise ConflictError("Two-step login is already on. Turn it off before setting up a new device.", code="mfa_already_on")
        secret = totp.new_secret()
        self.user.mfa_pending_secret = seal_secret(self.settings, secret)
        await self.session.commit()
        return {
            "secret": secret,
            "otpauth_uri": totp.provisioning_uri(secret, account=self.user.email, issuer=self.settings.mfa_issuer),
        }

    async def confirm_mfa(self, code: str) -> list[str]:
        if self.user.mfa_enabled:
            raise ConflictError("Two-step login is already on.", code="mfa_already_on")
        if not self.user.mfa_pending_secret:
            raise BadRequestError("Start the setup first.", code="mfa_not_started")
        secret = open_secret(self.settings, self.user.mfa_pending_secret)
        step = totp.verify(secret, code)
        if step is None:
            raise BadRequestError(_WRONG_CODE, code="mfa_invalid_code")
        codes, hashes = new_recovery_codes()
        self.user.mfa_secret = self.user.mfa_pending_secret
        self.user.mfa_pending_secret = None
        self.user.mfa_enabled = True
        self.user.mfa_last_step = step
        self.user.mfa_recovery_hashes = hashes
        await self.session.commit()
        return codes

    async def disable_mfa(self, password: str, code: str) -> None:
        await self._require_password(password)
        if not self.user.mfa_enabled:
            raise ConflictError("Two-step login is not on.", code="mfa_not_on")
        if not check_second_factor(self.settings, self.user, code):
            raise BadRequestError(_WRONG_CODE, code="mfa_invalid_code")
        self.user.mfa_enabled = False
        self.user.mfa_secret = None
        self.user.mfa_pending_secret = None
        self.user.mfa_last_step = None
        self.user.mfa_recovery_hashes = None
        await self.session.commit()

    async def renew_recovery_codes(self, password: str, code: str) -> list[str]:
        await self._require_password(password)
        if not self.user.mfa_enabled:
            raise ConflictError("Two-step login is not on.", code="mfa_not_on")
        if not check_second_factor(self.settings, self.user, code):
            raise BadRequestError(_WRONG_CODE, code="mfa_invalid_code")
        codes, hashes = new_recovery_codes()
        self.user.mfa_recovery_hashes = hashes
        await self.session.commit()
        return codes
