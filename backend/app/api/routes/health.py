"""System health check endpoint."""

from fastapi import APIRouter, Request

from app.schemas.system import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health_check(request: Request) -> HealthResponse:
    """Return service health status and active runtime environment."""
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service="ai-research-assistant-api",
        environment=settings.app_environment,
    )