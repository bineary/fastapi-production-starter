import uuid

from sqlalchemy import Select, select, tuple_

from app.core.pagination import Cursor
from app.models.enums import TaskPriority, TaskStatus
from app.models.task import Task
from app.repositories.base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    model = Task

    async def get_by_id_for_org(
        self, task_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Task | None:
        result = await self.session.execute(
            select(Task).where(Task.id == task_id, Task.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        project_id: uuid.UUID | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        assignee_id: uuid.UUID | None = None,
        title_contains: str | None = None,
        cursor: Cursor | None = None,
        limit: int = 20,
    ) -> list[Task]:
        stmt: Select[tuple[Task]] = select(Task).where(Task.organization_id == organization_id)

        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if priority is not None:
            stmt = stmt.where(Task.priority == priority)
        if assignee_id is not None:
            stmt = stmt.where(Task.assignee_id == assignee_id)
        if title_contains:
            stmt = stmt.where(Task.title.ilike(f"%{title_contains}%"))

        if cursor is not None:
            stmt = stmt.where(tuple_(Task.created_at, Task.id) < (cursor.created_at, cursor.id))

        stmt = stmt.order_by(Task.created_at.desc(), Task.id.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
