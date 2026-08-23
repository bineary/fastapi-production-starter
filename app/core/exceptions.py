from typing import Any


class AppError(Exception):
    """Base of the app's domain error hierarchy.

    Services and repositories raise these — never FastAPI's HTTPException,
    which would leak a web-framework dependency into layers that must stay
    framework-agnostic. The single exception handler in app/main.py maps
    these to RFC 9457 application/problem+json responses.
    """

    status_code: int = 500
    error_type: str = "about:blank"
    title: str = "Internal Server Error"

    def __init__(self, detail: str | None = None, **extra: Any) -> None:
        self.detail = detail or self.title
        self.extra = extra
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    error_type = "/problems/not-found"
    title = "Not Found"


class ConflictError(AppError):
    status_code = 409
    error_type = "/problems/conflict"
    title = "Conflict"


class UnauthorizedError(AppError):
    status_code = 401
    error_type = "/problems/unauthorized"
    title = "Unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    error_type = "/problems/forbidden"
    title = "Forbidden"


class DomainValidationError(AppError):
    """A business-rule validation failure (as opposed to request-shape 422s,
    which FastAPI/Pydantic raise as RequestValidationError before a service
    ever runs)."""

    status_code = 422
    error_type = "/problems/validation-error"
    title = "Validation Error"


class RateLimitedError(AppError):
    status_code = 429
    error_type = "/problems/rate-limited"
    title = "Too Many Requests"

    def __init__(self, retry_after_seconds: int, detail: str | None = None) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(detail)
