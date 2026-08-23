from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text

from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.comments import router as comments_router
from app.api.v1.routers.projects import router as projects_router
from app.api.v1.routers.tasks import router as tasks_router
from app.core.config import get_settings
from app.core.dependencies import DbSession
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.core.redis import get_redis

settings = get_settings()
configure_logging(settings)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("app.startup", environment=settings.environment)
    yield
    logger.info("app.shutdown")


API_DESCRIPTION = """
A multi-tenant Task Board API — `Organization → User → Project → Task → Comment`.

Every resource below the organization is scoped to it: authenticate as a
member of one organization and you'll only ever see that organization's
data, enforced at the query level (not just in the UI).

### Auth
OAuth2 password flow. Register creates a brand-new organization and its
first (`owner`) user; login exchanges credentials for a 15-minute access
token and a 7-day refresh token. Refresh tokens rotate on every use and
detect reuse — presenting an already-used token revokes the entire
session chain it belongs to, not just that one token.

### Roles
`member` < `admin` < `owner`, each including the permissions of the ones
below it. Project and task deletion require `admin`; most other actions
only require `member`.

### Errors
Every error response is `application/problem+json` ([RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)),
with a `trace_id` you can correlate against server logs.
""".strip()

OPENAPI_TAGS = [
    {
        "name": "auth",
        "description": "Registration, login, token refresh, and password/email flows.",
    },
    {"name": "projects", "description": "Top-level containers for tasks."},
    {
        "name": "tasks",
        "description": "The unit of work — has a status, priority, and optional assignee.",
    },
    {"name": "comments", "description": "Threaded discussion on a task."},
    {"name": "health", "description": "Liveness/readiness probes for orchestrators."},
    {"name": "observability", "description": "Prometheus metrics."},
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Task Board API",
        description=API_DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
        openapi_tags=OPENAPI_TAGS,
    )

    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/health/live", tags=["health"], summary="Liveness probe")
    async def health_live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get(
        "/health/ready",
        tags=["health"],
        summary="Readiness probe (checks DB + Redis)",
    )
    async def health_ready(db: DbSession) -> JSONResponse:
        checks = {"database": False, "redis": False}

        try:
            await db.execute(text("SELECT 1"))
            checks["database"] = True
        except Exception:
            logger.exception("health_ready.database_check_failed")

        try:
            await get_redis().ping()
            checks["redis"] = True
        except Exception:
            logger.exception("health_ready.redis_check_failed")

        ready = all(checks.values())
        return JSONResponse(
            status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "ready" if ready else "not_ready", "checks": checks},
        )

    Instrumentator().instrument(app).expose(app, endpoint="/metrics", tags=["observability"])

    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(projects_router, prefix=settings.api_v1_prefix)
    app.include_router(tasks_router, prefix=settings.api_v1_prefix)
    app.include_router(comments_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
