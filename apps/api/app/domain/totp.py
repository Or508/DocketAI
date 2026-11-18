"""Time-based one-time codes (RFC 6238), the six digits an authenticator app shows.

SHA-1, 30-second steps, six digits: what Google Authenticator, Microsoft Authenticator and
1Password expect by default. A code is accepted one step early or late, for clock drift, and
never twice: the caller keeps the last step used and passes it back.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

STEP_SECONDS = 30
DIGITS = 6
_DRIFT_STEPS = 1


def new_secret() -> str:
    """A random 160-bit secret, base32 without padding, the form apps accept when typed in."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret.upper() + "=" * (-len(secret) % 8)
    return base64.b32decode(padded)


def code_at(secret: str, step: int) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def current_step(now: float | None = None) -> int:
    return int((time.time() if now is None else now) // STEP_SECONDS)


def verify(secret: str, code: str, *, last_step: int | None = None, now: float | None = None) -> int | None:
    """The step the code belongs to when it is valid and not used before, else None."""
    cleaned = "".join(code.split())
    if len(cleaned) != DIGITS or not cleaned.isdigit():
        return None
    middle = current_step(now)
    for step in range(middle - _DRIFT_STEPS, middle + _DRIFT_STEPS + 1):
        if last_step is not None and step <= last_step:
            continue
        if hmac.compare_digest(code_at(secret, step), cleaned):
            return step
    return None


def provisioning_uri(secret: str, *, account: str, issuer: str) -> str:
    """The otpauth:// link a QR code carries, so an app adds the account in one scan."""
    label = quote(f"{issuer}:{account}")
    query = urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": STEP_SECONDS})
    return f"otpauth://totp/{label}?{query}"
