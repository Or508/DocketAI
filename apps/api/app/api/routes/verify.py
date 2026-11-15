from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.verify import SealVerification
from app.services.verify_service import verify_file, verify_seal

# Public: anyone holding a verification code, or the signed file, may check it.
# No session, no office scope.
router = APIRouter(prefix="/verify", tags=["verify"])

_SHA256 = r"^\s*[0-9a-fA-F]{64}\s*$"


@router.get("/by-hash/{sha256}", response_model=SealVerification)
async def verify_by_hash(
    response: Response,
    sha256: str = Path(pattern=_SHA256),
    session: AsyncSession = Depends(get_session),
) -> SealVerification:
    response.headers["Cache-Control"] = "no-store"
    return await verify_file(session, sha256)


@router.get("/{verification_id}", response_model=SealVerification)
async def verify(
    verification_id: str,
    response: Response,
    sha256: str | None = Query(default=None, pattern=_SHA256),
    session: AsyncSession = Depends(get_session),
) -> SealVerification:
    response.headers["Cache-Control"] = "no-store"
    return await verify_seal(session, verification_id, sha256)
