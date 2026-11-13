import httpx
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.schemas.system import HealthResponse, ReadinessCheck, ReadinessResponse

router = APIRouter(tags=["system"])
READINESS_TIMEOUT_SECONDS = 3.0


@router.get("/health", response_model=HealthResponse)
@router.get("/health/live", response_model=HealthResponse, include_in_schema=False)
def health_check(request: Request) -> HealthResponse:
    """Liveness: the process is up and serving requests."""
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service="ai-research-assistant-api",
        environment=settings.app_environment,
    )


def _check_database(request: Request) -> ReadinessCheck:
    engine = request.app.state.db_engine
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if engine.dialect.name == "postgresql":
                has_vector = connection.execute(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                ).scalar()
                if not has_vector:
                    return ReadinessCheck(name="database", ok=False, detail="pgvector extension missing")
        return ReadinessCheck(name="database", ok=True, detail=engine.dialect.name)
    except Exception as exc:  # noqa: BLE001 - report, never raise
        return ReadinessCheck(name="database", ok=False, detail=type(exc).__name__)


def _check_ollama(request: Request) -> ReadinessCheck:
    settings = request.app.state.settings
    try:
        response = httpx.get(
            f"{settings.ollama_base_url.rstrip('/')}/api/tags",
            timeout=READINESS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        names = {model.get("name") for model in response.json().get("models", [])}
    except Exception as exc:  # noqa: BLE001 - report, never raise
        return ReadinessCheck(name="ollama", ok=False, detail=type(exc).__name__)
    if settings.generation_model_name not in names:
        return ReadinessCheck(
            name="ollama",
            ok=False,
            detail=f"model {settings.generation_model_name} is not installed",
        )
    return ReadinessCheck(name="ollama", ok=True, detail=settings.generation_model_name)


def _check_llm_router(request: Request) -> ReadinessCheck:
    settings = request.app.state.settings
    key_by_provider = {
        "cerebras": bool(settings.cerebras_api_key),
        "gemini": bool(settings.gemini_api_key),
        "mistral": bool(settings.mistral_api_key),
        "openrouter": bool(settings.openrouter_api_key),
        "ollama": True,
    }
    raw_order = settings.llm_router_providers
    order = (
        [item.strip().lower() for item in raw_order.split(",") if item.strip()]
        if isinstance(raw_order, str)
        else [str(item).strip().lower() for item in raw_order if str(item).strip()]
    )
    configured = [
        name
        for name in order
        if name in key_by_provider and (key_by_provider[name] if name != "ollama" else True)
    ]
    if configured:
        return ReadinessCheck(
            name="llm_router",
            ok=True,
            detail=",".join(configured),
        )
    return ReadinessCheck(
        name="llm_router",
        ok=False,
        detail="no cloud LLM provider keys configured",
    )


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness_check(request: Request) -> JSONResponse:
    """Readiness: dependencies needed to serve real traffic are reachable."""
    settings = request.app.state.settings
    if settings.generation_runtime.strip().lower() == "router":
        llm_check = await run_in_threadpool(_check_llm_router, request)
    else:
        llm_check = await run_in_threadpool(_check_ollama, request)
    checks = [
        await run_in_threadpool(_check_database, request),
        llm_check,
    ]
    ready = all(check.ok for check in checks)
    body = ReadinessResponse(status="ready" if ready else "not_ready", checks=checks)
    return JSONResponse(
        status_code=200 if ready else 503,
        content=body.model_dump(by_alias=True),
    )
