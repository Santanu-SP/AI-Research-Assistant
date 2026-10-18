"""Standardized application error hierarchy and FastAPI exception handler.

All expected domain and service errors raise ``AppError``, which is serialized
into a consistent ``{"error": {"code": ..., "message": ...}}`` JSON envelope.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base exception for expected application-level failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "application_error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    """Serialize an ``AppError`` into a structured HTTP JSON response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
            }
        },
    )