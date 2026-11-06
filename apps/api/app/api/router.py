from fastapi import APIRouter

from app.api.routes import cases, health, portal, processes, signing_links

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(processes.router)
api_router.include_router(cases.router)
api_router.include_router(signing_links.router)
api_router.include_router(portal.router)
