from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from app.api.downloads import content_disposition
from app.core.container import Container
from app.domain.certificate import SignerContext, clean_ip, clean_user_agent
from app.core.deps import get_case_service, get_container
from app.db.session import get_session
from app.schemas.case import CaseCreate, CaseRead
from app.schemas.chat import ChatRequest, FieldUpdateRequest
from app.schemas.forms import DocumentRoleRead, DocumentRoleUpdate, FillReport, IntakeSummary
from app.schemas.gap import FillAndSignRequest, GapReport, ManualClassifyRequest
from app.schemas.workspace import CaseWorkspace, UploadResult
from app.services.case_service import CaseService
from app.services.chat_stream import iter_chat_stream
from app.services.progress_events import iter_case_progress
from app.workers.queue import enqueue_case_processing
from app.workers.runner import process_case_job

_STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("", response_model=list[CaseRead])
async def list_cases(service: CaseService = Depends(get_case_service)) -> list[CaseRead]:
    return await service.list_cases()


@router.post("", response_model=CaseRead, status_code=201)
async def create_case(
    payload: CaseCreate,
    service: CaseService = Depends(get_case_service),
) -> CaseRead:
    return await service.create_case(payload)


@router.get("/{case_id}", response_model=CaseWorkspace)
async def get_case(case_id: UUID, service: CaseService = Depends(get_case_service)) -> CaseWorkspace:
    return await service.workspace(case_id)


@router.get("/{case_id}/status", response_model=GapReport)
async def case_status(case_id: UUID, service: CaseService = Depends(get_case_service)) -> GapReport:
    return await service.gap(case_id)


@router.get("/{case_id}/events")
async def case_events(
    case_id: UUID,
    service: CaseService = Depends(get_case_service),
) -> StreamingResponse:
    await service.workspace(case_id)
    await service.session.commit()
    return StreamingResponse(
        iter_case_progress(case_id, service.scope),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


@router.post("/{case_id}/upload", response_model=UploadResult)
async def upload_documents(
    case_id: UUID,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    document_type: str | None = Form(default=None, max_length=64),
    role: str | None = Form(default=None, max_length=16),
    replace_existing: bool = Form(default=False),
    service: CaseService = Depends(get_case_service),
    container: Container = Depends(get_container),
) -> UploadResult:
    result, schedule = await service.add_uploads(case_id, files, document_type, role, replace_existing)
    if schedule:
        job_id = await enqueue_case_processing(case_id)
        if job_id is None:
            background_tasks.add_task(process_case_job, case_id, container)
        result.job_id = job_id
    return result


@router.post("/{case_id}/classify-manual", response_model=CaseWorkspace)
async def classify_manual(
    case_id: UUID,
    payload: ManualClassifyRequest,
    service: CaseService = Depends(get_case_service),
) -> CaseWorkspace:
    return await service.classify_manual(case_id, payload)


@router.post("/{case_id}/chat", response_model=CaseWorkspace)
async def chat(
    case_id: UUID,
    payload: ChatRequest,
    service: CaseService = Depends(get_case_service),
) -> CaseWorkspace:
    return await service.chat(case_id, payload)


@router.post("/{case_id}/chat/stream")
async def chat_stream(
    case_id: UUID,
    payload: ChatRequest,
    service: CaseService = Depends(get_case_service),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    await service.workspace(case_id)
    await service.session.commit()
    return StreamingResponse(
        iter_chat_stream(case_id, payload, container, service.scope),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


@router.post("/{case_id}/fields", response_model=CaseWorkspace)
async def set_field(
    case_id: UUID,
    payload: FieldUpdateRequest,
    service: CaseService = Depends(get_case_service),
) -> CaseWorkspace:
    return await service.set_field(case_id, payload)


@router.post("/{case_id}/fill-and-sign", response_model=CaseWorkspace)
async def fill_and_sign(
    case_id: UUID,
    payload: FillAndSignRequest,
    request: Request,
    service: CaseService = Depends(get_case_service),
) -> CaseWorkspace:
    reported_ip = request.headers.get("x-office-client-ip")
    host = reported_ip.strip() if reported_ip and reported_ip.strip() else (request.client.host if request.client else None)
    reported_agent = request.headers.get("x-office-user-agent")
    agent = reported_agent if reported_agent and reported_agent.strip() else request.headers.get("user-agent")
    context = SignerContext("office", clean_ip(host), clean_user_agent(agent))
    return await service.fill_and_sign(case_id, payload, context)


@router.get("/{case_id}/certificate")
async def download_certificate(
    case_id: UUID,
    service: CaseService = Depends(get_case_service),
) -> Response:
    data = await service.certificate_pdf(case_id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="certificate.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{case_id}/documents/{document_id}/file")
async def download_document(
    case_id: UUID,
    document_id: UUID,
    service: CaseService = Depends(get_case_service),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    reader, mime_type, filename = await service.document_file(case_id, document_id)
    # Release the database connection before a long download starts.
    try:
        await session.commit()
    except Exception:
        reader.close()
        raise
    return StreamingResponse(
        reader.chunks,
        media_type=mime_type,
        headers={
            "Content-Disposition": content_disposition(filename),
            "Content-Length": str(reader.size),
            "Cache-Control": "no-store",
        },
        background=BackgroundTask(reader.close),
    )


@router.delete("/{case_id}/documents/{document_id}", response_model=CaseWorkspace)
async def delete_document(
    case_id: UUID,
    document_id: UUID,
    service: CaseService = Depends(get_case_service),
) -> CaseWorkspace:
    return await service.delete_document(case_id, document_id)


@router.put("/{case_id}/documents/{document_id}/role", response_model=DocumentRoleRead)
async def set_document_role(
    case_id: UUID,
    document_id: UUID,
    payload: DocumentRoleUpdate,
    service: CaseService = Depends(get_case_service),
) -> DocumentRoleRead:
    return await service.set_document_role(case_id, document_id, payload)


@router.get("/{case_id}/documents/{document_id}/filled-preview")
async def filled_preview(
    case_id: UUID,
    document_id: UUID,
    service: CaseService = Depends(get_case_service),
) -> Response:
    data = await service.filled_preview(case_id, document_id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "inline",
            "Cache-Control": "no-store",
        },
    )


@router.get("/{case_id}/documents/{document_id}/fill-report", response_model=FillReport)
async def fill_report(
    case_id: UUID,
    document_id: UUID,
    service: CaseService = Depends(get_case_service),
) -> FillReport:
    return await service.fill_report(case_id, document_id)


@router.get("/{case_id}/intake", response_model=IntakeSummary)
async def intake_summary(
    case_id: UUID,
    service: CaseService = Depends(get_case_service),
) -> IntakeSummary:
    return await service.intake(case_id)


@router.get("/{case_id}/signed-document")
async def download_signed_document(
    case_id: UUID,
    service: CaseService = Depends(get_case_service),
) -> Response:
    data, filename = await service.signed_pdf(case_id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition(filename),
            "Cache-Control": "no-store",
        },
    )
