from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.security import create_purpose_token, hash_password, hash_refresh_token
from app.models.enums import OrgRole
from app.models.organization import Organization
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import (
    EMAIL_VERIFICATION_PURPOSE,
    AuthService,
)
from app.services.email_sender import ConsoleEmailSender

pytestmark = pytest.mark.integration


async def _make_service(db_session: AsyncSession) -> AuthService:
    return AuthService(db_session, get_settings(), ConsoleEmailSender())


async def _make_user(db_session: AsyncSession, *, is_active: bool = True) -> User:
    org = await OrganizationRepository(db_session).add(Organization(name="Edge Co", slug="edge-co"))
    user = await UserRepository(db_session).add(
        User(
            organization_id=org.id,
            email="edge@example.com",
            hashed_password=hash_password("a-strong-password-123"),
            full_name="Edge Case",
            role=OrgRole.OWNER,
            is_active=is_active,
        )
    )
    await db_session.commit()
    return user


async def test_authenticate_rejects_inactive_user(db_session: AsyncSession) -> None:
    await _make_user(db_session, is_active=False)
    service = await _make_service(db_session)

    with pytest.raises(UnauthorizedError):
        await service.authenticate(email="edge@example.com", password="a-strong-password-123")


async def test_refresh_with_unknown_token_is_unauthorized(db_session: AsyncSession) -> None:
    service = await _make_service(db_session)

    with pytest.raises(UnauthorizedError):
        await service.refresh("this-token-was-never-issued")


async def test_refresh_with_expired_token_is_unauthorized(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    service = await _make_service(db_session)
    tokens = await service.issue_token_pair(user)

    # Force the freshly issued refresh token to already be expired.
    token_row = await service.refresh_tokens.get_by_token_hash(
        hash_refresh_token(tokens.refresh_token)
    )
    assert token_row is not None
    token_row.expires_at = token_row.issued_at - timedelta(seconds=1)
    await db_session.commit()

    with pytest.raises(UnauthorizedError):
        await service.refresh(tokens.refresh_token)


async def test_verify_email_with_expired_token_is_unauthorized(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    service = await _make_service(db_session)

    already_expired_token = create_purpose_token(
        user_id=user.id,
        purpose=EMAIL_VERIFICATION_PURPOSE,
        expires_delta=timedelta(seconds=-1),
        settings=get_settings(),
    )

    with pytest.raises(UnauthorizedError):
        await service.verify_email(already_expired_token)
