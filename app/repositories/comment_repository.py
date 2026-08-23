import uuid

from sqlalchemy import select

from app.models.comment import Comment
from app.repositories.base import BaseRepository


class CommentRepository(BaseRepository[Comment]):
    model = Comment

    async def get_by_id_for_org(
        self, comment_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Comment | None:
        result = await self.session.execute(
            select(Comment).where(
                Comment.id == comment_id, Comment.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_task(self, task_id: uuid.UUID, organization_id: uuid.UUID) -> list[Comment]:
        result = await self.session.execute(
            select(Comment)
            .where(Comment.task_id == task_id, Comment.organization_id == organization_id)
            .order_by(Comment.created_at)
        )
        return list(result.scalars().all())
