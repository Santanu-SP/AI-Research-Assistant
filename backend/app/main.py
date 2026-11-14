from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.rate_limit import RateLimiter
from app.db.session import create_db_engine, create_session_factory
from app.services.jobs.worker import JobWorker

# Room for multipart boundaries and headers around the uploaded file.
MULTIPART_OVERHEAD_BYTES = 1024 * 1024


def create_app(app_settings: Settings | None = None) -> FastAPI:
    active_settings = app_settings or settings
    configure_logging(active_settings.log_level, json_logs=active_settings.log_json)
    engine = create_db_engine(
        active_settings.database_url,
        pool_size=active_settings.db_pool_size,
        max_overflow=active_settings.db_max_overflow,
        pool_timeout=active_settings.db_pool_timeout_seconds,
        pool_recycle=active_settings.db_pool_recycle_seconds,
        pool_use_lifo=active_settings.db_pool_use_lifo,
    )
    session_factory = create_session_factory(engine)
    worker = JobWorker(session_factory, active_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        active_settings.validate_production_startup()
        if active_settings.worker_enabled:
            worker.start()
        try:
            yield
        finally:
            worker.stop()
            engine.dispose()

    docs_enabled = active_settings.api_docs_enabled
    application = FastAPI(
        title=active_settings.app_name,
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.db_engine = engine
    application.state.db_session_factory = session_factory
    application.state.job_worker = worker
    application.state.rate_limiter = RateLimiter()

    # Middleware runs in reverse order of registration: the request id is
    # assigned first, then body limits, headers, and CORS.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_origin_regex=active_settings.effective_cors_origin_regex,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    application.add_middleware(
        SecurityHeadersMiddleware,
        hsts=bool(active_settings.auth_cookie_secure),
    )
    application.add_middleware(
        BodySizeLimitMiddleware,
        default_limit=active_settings.max_json_body_bytes,
        upload_limit=active_settings.document_max_upload_bytes + MULTIPART_OVERHEAD_BYTES,
    )
    application.add_middleware(RequestContextMiddleware)
    register_error_handlers(application)
    application.include_router(api_router, prefix=active_settings.api_v1_prefix)
    return application


app = create_app()
