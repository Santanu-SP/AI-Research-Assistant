from fastapi import APIRouter

from app.api.routes.documents import router as documents_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.projects import router as projects_router
from app.api.routes.project_documents import router as project_documents_router
from app.api.routes.project_sources import router as project_sources_router
from app.api.routes.research import router as research_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(health_router)
api_router.include_router(projects_router)
api_router.include_router(project_documents_router)
api_router.include_router(project_sources_router)
api_router.include_router(research_router)
api_router.include_router(documents_router)
