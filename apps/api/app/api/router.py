from fastapi import APIRouter, Depends

from app.api.routes import analytics, auth, cases, health, portal, processes, signing_links, templates, verify
from app.core.deps import current_user

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
_office = [Depends(current_user)]
api_router.include_router(processes.router, dependencies=_office)
api_router.include_router(cases.router, dependencies=_office)
api_router.include_router(templates.router, dependencies=_office)
api_router.include_router(analytics.router, dependencies=_office)
api_router.include_router(signing_links.router, dependencies=_office)
api_router.include_router(portal.router)
api_router.include_router(verify.router)
