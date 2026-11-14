"""One error envelope for every failure the API returns.

Every error body has the shape ``{"error": {"code": ..., "message": ...}}``.
Validation failures add a ``details`` list so the frontend can point at the
offending field.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

HTTP_ERROR_CODES = {
    400: "bad_request",
    401: "authentication_required",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "request_too_large",
    415: "unsupported_media_type",
    429: "rate_limited",
}


class AppError(Exception):
    """Base exception for expected application-level failures."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "application_error",
        headers: dict[str, str] | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.headers = headers
        # Small, safe extras for the client, e.g. the id of the research run
        # a failed request belongs to.
        self.details = details


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: list[dict[str, object]] | dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return JSONResponse(
        status_code=status_code,
        content={"error": body},
        headers=headers,
    )


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return error_response(
        exc.status_code,
        exc.code,
        exc.message,
        details=exc.details,
        headers=exc.headers,
    )


async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = HTTP_ERROR_CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return error_response(
        exc.status_code,
        code,
        message,
        headers=getattr(exc, "headers", None),
    )


async def validation_error_handler(
    _: Request, exc: RequestValidationError
) -> JSONResponse:
    details = []
    for item in exc.errors():
        details.append(
            {
                "loc": list(item.get("loc", ())),
                "msg": item.get("msg", "Invalid value"),
                "type": item.get("type", "value_error"),
            }
        )
    first = details[0]["msg"] if details else "The request is invalid"
    return error_response(
        422,
        "validation_error",
        str(first),
        details=jsonable_encoder(details),
    )


async def pool_timeout_handler(_: Request, exc: PoolTimeoutError) -> JSONResponse:
    logger.warning("Database connection pool exhausted: %s", exc)
    return error_response(
        503,
        "service_busy",
        "The service is busy. Please retry in a moment.",
        headers={"Retry-After": "2"},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled error on %s %s", request.method, request.url.path, exc_info=exc
    )
    return error_response(
        500,
        "internal_error",
        "Something went wrong on our side. Please try again.",
    )


def register_error_handlers(application: FastAPI) -> None:
    application.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(StarletteHTTPException, http_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    application.add_exception_handler(PoolTimeoutError, pool_timeout_handler)  # type: ignore[arg-type]
    application.add_exception_handler(Exception, unhandled_error_handler)
