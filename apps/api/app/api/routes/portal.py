from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.core.container import Container
from app.domain.certificate import SignerContext, clean_ip, clean_user_agent
from app.api.downloads import content_disposition
from app.core.deps import bearer_token, get_container, get_portal_service
from app.core.exceptions import ConflictError
from app.core.time import utcnow
from app.domain.signing_links import link_state
from app.models.case import Case
from app.models.signing_link import SigningLink
from app.schemas.chat import ChatRequest, FieldUpdateRequest
from app.schemas.portal import PortalSignRequest, PortalView
from app.services.chat_stream import iter_chat_stream
from app.services.portal_service import PortalService

router = APIRouter(prefix="/portal", tags=["portal"])
_STREAM_HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}


async def _open_link(
    token: str = Depends(bearer_token),
    service: PortalService = Depends(get_portal_service),
) -> tuple[SigningLink, Case, PortalService]:
    link, case = await service.resolve(token)
    service.require_open(link, case)
    return link, case, service


@router.get("", response_model=PortalView)
async def portal_view(
    token: str = Depends(bearer_token),
    service: PortalService = Depends(get_portal_service),
) -> PortalView:
    link, case = await service.resolve(token)
    return service.view(link, case)


@router.get("/preview")
async def portal_preview(
    opened: tuple[SigningLink, Case, PortalService] = Depends(_open_link),
) -> Response:
    _, case, service = opened
    pdf = await service.preview_pdf(case)
    return Response(content=pdf, media_type="application/pdf", headers={"Cache-Control": "no-store"})


@router.post("/fields", response_model=PortalView)
async def portal_fields(
    payload: FieldUpdateRequest,
    opened: tuple[SigningLink, Case, PortalService] = Depends(_open_link),
) -> PortalView:
    link, case, service = opened
    await service.cases.set_field(case.id, payload, reject_if_signed=True)
    stored = await service.cases._get_case(case.id)
    current = await service.session.get(SigningLink, link.id)
    assert current is not None
    return service.view(current, stored)


@router.post("/chat/stream")
async def portal_chat(
    payload: ChatRequest,
    opened: tuple[SigningLink, Case, PortalService] = Depends(_open_link),
    container: Container = Depends(get_container),
) -> StreamingResponse:
    link, case, service = opened
    link_id = link.id
    await service.consume_chat_turn(link)

    async def render(case_service, case_id: UUID) -> BaseModel:
        current = await case_service.session.get(SigningLink, link_id)
        if current is None:
            raise ConflictError("This link is no longer active.")
        stored = await case_service._get_case(case_id)
        return PortalService(case_service.session, container, service.scope).view(current, stored)

    return StreamingResponse(
        iter_chat_stream(
            case.id,
            payload,
            container,
            service.scope,
            render=render,
            reject_if_signed=True,
        ),
        media_type="text/event-stream",
        headers=_STREAM_HEADERS,
    )


@router.post("/sign", response_model=PortalView)
async def portal_sign(
    payload: PortalSignRequest,
    request: Request,
    opened: tuple[SigningLink, Case, PortalService] = Depends(_open_link),
) -> PortalView:
    link, case, service = opened
    context = SignerContext(
        "portal",
        clean_ip(request.headers.get("x-portal-client-ip")),
        clean_user_agent(request.headers.get("x-portal-user-agent")),
    )
    await service.sign(link, case, payload, context)
    stored_link = await service.session.get(SigningLink, link.id)
    stored_case = await service.cases._get_case(case.id)
    assert stored_link is not None
    return service.view(stored_link, stored_case)


@router.get("/signed-document")
async def portal_download(
    token: str = Depends(bearer_token),
    service: PortalService = Depends(get_portal_service),
) -> Response:
    link, case = await service.resolve(token)
    if link_state(link, case, utcnow()) != "completed":
        raise ConflictError("The signed copy is not available.")
    data, _filename = await service.cases.signed_pdf(case.id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition("signed-document.pdf"),
            "Cache-Control": "no-store",
        },
    )


@router.get("/certificate")
async def portal_certificate(
    token: str = Depends(bearer_token),
    service: PortalService = Depends(get_portal_service),
) -> Response:
    link, case = await service.resolve(token)
    if link_state(link, case, utcnow()) != "completed":
        raise ConflictError("The signed copy is not available.")
    data = await service.cases.certificate_pdf(case.id)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": content_disposition("certificate-of-completion.pdf"),
            "Cache-Control": "no-store",
        },
    )
