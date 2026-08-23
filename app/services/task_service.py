import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainValidationError, NotFoundError
from app.core.pagination import Cursor
from app.models.enums import TaskPriority, TaskStatus
from app.models.task import Task
from app.repositories.project_repository import ProjectRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository
from app.schemas.task import TaskCreate, TaskUpdate


@dataclass(frozen=True)
class TaskPage:
    items: list[Task]
    next_cursor: Cursor | None


class TaskService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tasks = TaskRepository(session)
        self.projects = ProjectRepository(session)
        self.users = UserRepository(session)

    async def _assert_assignee_in_org(
        self, assignee_id: uuid.UUID, organization_id: uuid.UUID
    ) -> None:
        assignee = await self.users.get_by_id_for_org(assignee_id, organization_id)
        if assignee is None:
            raise DomainValidationError("Assignee must belong to the same organization")

    async def create(
        self, *, organization_id: uuid.UUID, created_by_id: uuid.UUID | None, data: TaskCreate
    ) -> Task:
        project = await self.projects.get_by_id_for_org(data.project_id, organization_id)
        if project is None:
            raise NotFoundError("Project not found")

        if data.assignee_id is not None:
            await self._assert_assignee_in_org(data.assignee_id, organization_id)

        task = await self.tasks.add(
            Task(
                organization_id=organization_id,
                project_id=data.project_id,
                created_by_id=created_by_id,
                title=data.title,
                description=data.description,
                status=data.status,
                priority=data.priority,
                assignee_id=data.assignee_id,
                due_date=data.due_date,
            )
        )
        await self.session.commit()
        return task

    async def get(self, task_id: uuid.UUID, organization_id: uuid.UUID) -> Task:
        task = await self.tasks.get_by_id_for_org(task_id, organization_id)
        if task is None:
            raise NotFoundError("Task not found")
        return task

    async def list(
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
    ) -> TaskPage:
        rows = await self.tasks.list_for_org(
            organization_id,
            project_id=project_id,
            status=status,
            priority=priority,
            assignee_id=assignee_id,
            title_contains=title_contains,
            cursor=cursor,
            limit=limit + 1,
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = (
            Cursor(created_at=items[-1].created_at, id=items[-1].id) if has_more and items else None
        )
        return TaskPage(items=items, next_cursor=next_cursor)

    async def update(
        self, task_id: uuid.UUID, organization_id: uuid.UUID, data: TaskUpdate
    ) -> Task:
        task = await self.get(task_id, organization_id)
        updates = data.model_dump(exclude_unset=True)

        if updates.get("assignee_id") is not None:
            await self._assert_assignee_in_org(updates["assignee_id"], organization_id)

        for field, value in updates.items():
            setattr(task, field, value)
        await self.session.commit()
        # `updated_at` is server-computed (onupdate=func.now()); refresh so
        # the returned object reflects it instead of a stale/unloaded value.
        await self.session.refresh(task)
        return task

    async def delete(self, task_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        task = await self.get(task_id, organization_id)
        await self.tasks.delete(task)
        await self.session.commit()
