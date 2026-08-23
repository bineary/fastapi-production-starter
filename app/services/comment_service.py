import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.rbac import role_at_least
from app.models.comment import Comment
from app.models.enums import OrgRole
from app.models.user import User
from app.repositories.comment_repository import CommentRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.comment import CommentCreate


class CommentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.comments = CommentRepository(session)
        self.tasks = TaskRepository(session)

    async def _assert_task_in_org(self, task_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        if await self.tasks.get_by_id_for_org(task_id, organization_id) is None:
            raise NotFoundError("Task not found")

    async def create(
        self,
        *,
        task_id: uuid.UUID,
        organization_id: uuid.UUID,
        author_id: uuid.UUID,
        data: CommentCreate,
    ) -> Comment:
        await self._assert_task_in_org(task_id, organization_id)
        comment = await self.comments.add(
            Comment(
                organization_id=organization_id,
                task_id=task_id,
                author_id=author_id,
                body=data.body,
            )
        )
        await self.session.commit()
        return comment

    async def list_for_task(self, task_id: uuid.UUID, organization_id: uuid.UUID) -> list[Comment]:
        await self._assert_task_in_org(task_id, organization_id)
        return await self.comments.list_for_task(task_id, organization_id)

    async def delete(
        self,
        *,
        task_id: uuid.UUID,
        comment_id: uuid.UUID,
        organization_id: uuid.UUID,
        requesting_user: User,
    ) -> None:
        comment = await self.comments.get_by_id_for_org(comment_id, organization_id)
        if comment is None or comment.task_id != task_id:
            raise NotFoundError("Comment not found")

        is_author = comment.author_id == requesting_user.id
        is_privileged = role_at_least(requesting_user.role, OrgRole.ADMIN)
        if not (is_author or is_privileged):
            raise ForbiddenError("Only the comment's author or an admin can delete it")

        await self.comments.delete(comment)
        await self.session.commit()
