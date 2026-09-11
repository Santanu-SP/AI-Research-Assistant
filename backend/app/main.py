from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import Settings, settings
from app.core.errors import AppError, app_error_handler
from app.db.session import create_db_engine, create_session_factory


def create_app(app_settings: Settings | None = None) -> FastAPI:
    active_settings = app_settings or settings
    engine = create_db_engine(active_settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        engine.dispose()

    application = FastAPI(
        title=active_settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.db_engine = engine
    application.state.db_session_factory = create_session_factory(engine)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(api_router, prefix=active_settings.api_v1_prefix)
    return application


app = create_app()
