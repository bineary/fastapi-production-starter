import uuid
from typing import Generic, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Shared CRUD primitives. Subclasses add model-specific queries.

    Repositories never commit — the calling service owns the transaction
    boundary. `flush` is used where the caller needs a generated id/default
    back before the transaction ends.
    """

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id_: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, id_)

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()
