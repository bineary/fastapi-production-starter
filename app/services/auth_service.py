import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.security import (
    InvalidTokenError,
    create_access_token,
    create_purpose_token,
    decode_purpose_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.core.slug import slugify
from app.models.enums import OrgRole
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.email_sender import EmailSender

EMAIL_VERIFICATION_PURPOSE = "email_verification"
PASSWORD_RESET_PURPOSE = "password_reset"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(
        self, session: AsyncSession, settings: Settings, email_sender: EmailSender
    ) -> None:
        self.session = session
        self.settings = settings
        self.email_sender = email_sender
        self.users = UserRepository(session)
        self.organizations = OrganizationRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    async def register(
        self, *, organization_name: str, email: str, password: str, full_name: str
    ) -> User:
        if await self.users.get_by_email(email) is not None:
            raise ConflictError("A user with this email already exists")

        org = await self.organizations.add(
            Organization(name=organization_name, slug=slugify(organization_name))
        )
        user = await self.users.add(
            User(
                organization_id=org.id,
                email=email,
                hashed_password=hash_password(password),
                full_name=full_name,
                role=OrgRole.OWNER,
                is_active=True,
            )
        )
        await self.session.commit()

        await self._send_verification_email(user)
        return user

    async def authenticate(self, *, email: str, password: str) -> User:
        user = await self.users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Incorrect email or password")
        if not user.is_active:
            raise UnauthorizedError("User is inactive")
        return user

    async def issue_token_pair(
        self, user: User, *, family_id: uuid.UUID | None = None
    ) -> TokenPair:
        access_token = create_access_token(
            user_id=user.id,
            organization_id=user.organization_id,
            role=user.role,
            settings=self.settings,
        )
        raw_refresh_token = await self._issue_refresh_token(user, family_id or uuid.uuid4())
        await self.session.commit()
        return TokenPair(access_token=access_token, refresh_token=raw_refresh_token)

    async def _issue_refresh_token(self, user: User, family_id: uuid.UUID) -> str:
        raw_token = generate_refresh_token()
        now = datetime.now(UTC)
        await self.refresh_tokens.add(
            RefreshToken(
                user_id=user.id,
                family_id=family_id,
                token_hash=hash_refresh_token(raw_token),
                issued_at=now,
                expires_at=now + timedelta(days=self.settings.refresh_token_expire_days),
            )
        )
        return raw_token

    async def refresh(self, raw_refresh_token: str) -> TokenPair:
        token_row = await self.refresh_tokens.get_by_token_hash(
            hash_refresh_token(raw_refresh_token)
        )
        if token_row is None:
            raise UnauthorizedError("Invalid refresh token")

        now = datetime.now(UTC)

        if token_row.revoked_at is not None:
            # The token was already used (or explicitly revoked) and is being
            # presented again — that's theft, not a legitimate retry. Burn
            # the whole rotation family so a stolen token chain is dead too.
            await self.refresh_tokens.revoke_family(token_row.family_id, revoked_at=now)
            await self.session.commit()
            raise UnauthorizedError("Refresh token reuse detected; all sessions revoked")

        if token_row.expires_at < now:
            raise UnauthorizedError("Refresh token expired")

        user = await self.users.get_by_id(token_row.user_id)
        if user is None or not user.is_active:
            raise UnauthorizedError("User not found or inactive")

        await self.refresh_tokens.revoke(token_row, revoked_at=now)
        new_raw_token = await self._issue_refresh_token(user, token_row.family_id)

        new_token_row = await self.refresh_tokens.get_by_token_hash(
            hash_refresh_token(new_raw_token)
        )
        assert new_token_row is not None
        token_row.replaced_by_id = new_token_row.id

        access_token = create_access_token(
            user_id=user.id,
            organization_id=user.organization_id,
            role=user.role,
            settings=self.settings,
        )
        await self.session.commit()
        return TokenPair(access_token=access_token, refresh_token=new_raw_token)

    async def logout(self, raw_refresh_token: str) -> None:
        token_row = await self.refresh_tokens.get_by_token_hash(
            hash_refresh_token(raw_refresh_token)
        )
        if token_row is not None and token_row.revoked_at is None:
            await self.refresh_tokens.revoke(token_row, revoked_at=datetime.now(UTC))
            await self.session.commit()

    async def change_password(
        self, user: User, *, current_password: str, new_password: str
    ) -> None:
        if not verify_password(current_password, user.hashed_password):
            raise UnauthorizedError("Current password is incorrect")

        user.hashed_password = hash_password(new_password)
        # A password change invalidates every existing session, not just this one.
        await self.refresh_tokens.revoke_all_for_user(user.id, revoked_at=datetime.now(UTC))
        await self.session.commit()

    async def _send_verification_email(self, user: User) -> None:
        token = create_purpose_token(
            user_id=user.id,
            purpose=EMAIL_VERIFICATION_PURPOSE,
            expires_delta=timedelta(hours=24),
            settings=self.settings,
        )
        await self.email_sender.send(
            to=user.email,
            subject="Verify your email",
            body=f"Verify your email with this token: {token}",
        )

    async def verify_email(self, token: str) -> None:
        try:
            user_id = decode_purpose_token(
                token, expected_purpose=EMAIL_VERIFICATION_PURPOSE, settings=self.settings
            )
        except InvalidTokenError as exc:
            raise UnauthorizedError("Invalid or expired verification token") from exc

        user = await self.users.get_by_id(user_id)
        if user is None:
            raise UnauthorizedError("Invalid or expired verification token")

        user.is_email_verified = True
        await self.session.commit()

    async def request_password_reset(self, email: str) -> None:
        user = await self.users.get_by_email(email)
        if user is None:
            # Don't reveal whether the email is registered.
            return

        token = create_purpose_token(
            user_id=user.id,
            purpose=PASSWORD_RESET_PURPOSE,
            expires_delta=timedelta(hours=1),
            settings=self.settings,
        )
        await self.email_sender.send(
            to=user.email,
            subject="Reset your password",
            body=f"Reset your password with this token: {token}",
        )

    async def confirm_password_reset(self, *, token: str, new_password: str) -> None:
        try:
            user_id = decode_purpose_token(
                token, expected_purpose=PASSWORD_RESET_PURPOSE, settings=self.settings
            )
        except InvalidTokenError as exc:
            raise UnauthorizedError("Invalid or expired reset token") from exc

        user = await self.users.get_by_id(user_id)
        if user is None:
            raise UnauthorizedError("Invalid or expired reset token")

        user.hashed_password = hash_password(new_password)
        await self.refresh_tokens.revoke_all_for_user(user.id, revoked_at=datetime.now(UTC))
        await self.session.commit()
