"""FastAPI application factory and lifecycle configuration.

This module initializes the FastAPI application, binds the SQLAlchemy engine
and session factory to application state, configures CORS middleware, and
registers global exception handlers and API v1 routers.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, settings
from app.core.errors import AppError, app_error_handler
from app.db.session import create_db_engine, create_session_factory

APP_VERSION = "0.1.0"
DOCS_PATH = "/docs"
REDOC_PATH = "/redoc"


def _configure_cors_middleware(
    application: FastAPI,
    active_settings: Settings,
) -> None:
    """Attach CORS middleware using environment-aware origin rules."""
    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_origin_regex=active_settings.effective_cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def create_app(app_settings: Settings | None = None) -> FastAPI:
    """Construct and configure the FastAPI application instance.

    Args:
        app_settings: Optional custom settings override (used in isolated tests).
            Defaults to the cached global ``settings`` instance.
    """
    active_settings = app_settings or settings
    engine = create_db_engine(active_settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Dispose of the SQLAlchemy connection pool cleanly on shutdown."""
        yield
        engine.dispose()

    application = FastAPI(
        title=active_settings.app_name,
        version=APP_VERSION,
        docs_url=DOCS_PATH,
        redoc_url=REDOC_PATH,
        lifespan=lifespan,
    )

    # Store shared infrastructure objects on application state for dependency injection
    application.state.settings = active_settings
    application.state.db_engine = engine
    application.state.db_session_factory = create_session_factory(engine)

    _configure_cors_middleware(application, active_settings)
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(api_router, prefix=active_settings.api_v1_prefix)

    return application


app = create_app()