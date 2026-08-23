import uuid
from datetime import datetime

from sqlalchemy import select, update

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_token_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken, *, revoked_at: datetime) -> None:
        token.revoked_at = revoked_at
        await self.session.flush()

    async def revoke_family(self, family_id: uuid.UUID, *, revoked_at: datetime) -> None:
        """Revoke every still-active token in a rotation family.

        Called when a revoked token is presented again — the reuse signals
        the family may be compromised, so the whole chain is invalidated.
        """
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        await self.session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID, *, revoked_at: datetime) -> None:
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        await self.session.flush()
