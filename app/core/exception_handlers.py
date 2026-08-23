from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError, RateLimitedError

logger = structlog.get_logger(__name__)

PROBLEM_JSON = "application/problem+json"


def _trace_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _problem(
    request: Request,
    *,
    status_code: int,
    error_type: str,
    title: str,
    detail: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": error_type,
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
        "trace_id": _trace_id(request),
    }
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status_code, content=body, media_type=PROBLEM_JSON)


async def app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    response = _problem(
        request,
        status_code=exc.status_code,
        error_type=exc.error_type,
        title=exc.title,
        detail=exc.detail,
        extra=exc.extra or None,
    )
    if isinstance(exc, RateLimitedError):
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
    return response


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {
            "field": ".".join(str(p) for p in error["loc"] if p != "body"),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    return _problem(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        error_type="/problems/validation-error",
        title="Validation Error",
        detail="The request failed validation.",
        extra={"errors": errors},
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches routing-level HTTPExceptions Starlette raises before our own
    code runs (unmatched routes, method-not-allowed) so even those get the
    same problem+json shape instead of FastAPI's default {"detail": ...}."""
    assert isinstance(exc, StarletteHTTPException)
    return _problem(
        request,
        status_code=exc.status_code,
        error_type="about:blank",
        title=str(exc.detail),
        detail=str(exc.detail),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", exc_info=exc)
    return _problem(
        request,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_type="about:blank",
        title="Internal Server Error",
        detail="An unexpected error occurred.",
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
