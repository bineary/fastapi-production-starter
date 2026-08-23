from typing import Any

from app.schemas.problem import ProblemDetail, ValidationProblemDetail

NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ProblemDetail, "description": "The resource doesn't exist in your organization"}
}
FORBIDDEN: dict[int | str, dict[str, Any]] = {
    403: {"model": ProblemDetail, "description": "Your role doesn't permit this action"}
}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ProblemDetail, "description": "The resource already exists"}
}
UNAUTHORIZED: dict[int | str, dict[str, Any]] = {
    401: {"model": ProblemDetail, "description": "Missing, invalid, or expired credentials"}
}
VALIDATION: dict[int | str, dict[str, Any]] = {
    422: {"model": ValidationProblemDetail, "description": "Request failed validation"}
}
RATE_LIMITED: dict[int | str, dict[str, Any]] = {
    429: {"model": ProblemDetail, "description": "Too many requests — see the Retry-After header"}
}
