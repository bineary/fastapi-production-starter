from collections.abc import AsyncIterator, Callable
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, RateLimitedError, UnauthorizedError
from app.core.rbac import role_at_least
from app.core.redis import check_rate_limit, get_redis
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import async_session_factory
from app.models.enums import OrgRole
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.email_sender import ConsoleEmailSender, EmailSender

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login", auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


DbSession = Annotated[AsyncSession, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: DbSession,
    settings: SettingsDep,
) -> User:
    if token is None:
        raise UnauthorizedError("Not authenticated")

    try:
        payload = decode_access_token(token, settings)
    except InvalidTokenError as exc:
        raise UnauthorizedError("Invalid or expired access token") from exc

    user = await UserRepository(db).get_by_id(payload.sub)
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(minimum_role: OrgRole) -> Callable[[User], User]:
    """Dependency factory: allows the given role and anything ranked above it
    (owner > admin > member), matching how org permissions usually nest."""

    def _check(current_user: CurrentUser) -> User:
        if not role_at_least(current_user.role, minimum_role):
            raise ForbiddenError(f"Requires role '{minimum_role.value}' or higher")
        return current_user

    return _check


def get_email_sender() -> EmailSender:
    return ConsoleEmailSender()


EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]


async def enforce_auth_rate_limit(request: Request, settings: SettingsDep) -> None:
    client_ip = request.client.host if request.client else "unknown"
    allowed, retry_after_seconds = await check_rate_limit(
        get_redis(),
        key=f"auth:{client_ip}",
        max_requests=settings.rate_limit_auth_requests,
        window_seconds=settings.rate_limit_auth_window_seconds,
    )
    if not allowed:
        raise RateLimitedError(retry_after_seconds, "Too many auth requests, slow down")
