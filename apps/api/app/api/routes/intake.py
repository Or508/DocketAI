from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core.deps import get_intake_service
from app.schemas.intake import IntakeStatus, IntakeUploadResult
from app.services.intake_service import IntakeService

# Public: the token in the path is the only credential. No office session is read here.
# A token of the wrong shape is answered like an unknown one: not found.
router = APIRouter(prefix="/intake", tags=["intake"])


@router.get("/{token}", response_model=IntakeStatus)
async def intake_status(
    token: str,
    service: IntakeService = Depends(get_intake_service),
) -> IntakeStatus:
    """Which documents the case needs and which have arrived. No personal values."""
    return await service.status(token)


@router.post("/{token}/upload", response_model=IntakeUploadResult)
async def intake_upload(
    token: str,
    files: list[UploadFile] | None = File(default=None),
    file: UploadFile | None = File(default=None),
    document_type: str | None = Form(default=None, max_length=64),
    service: IntakeService = Depends(get_intake_service),
) -> IntakeUploadResult:
    """One to five files, or one file with the document type the client chose for it."""
    sent = list(files or [])
    if file is not None:
        sent.append(file)
    return await service.upload(token, sent, document_type)
