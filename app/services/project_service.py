import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.pagination import Cursor
from app.models.project import Project
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectUpdate


@dataclass(frozen=True)
class ProjectPage:
    items: list[Project]
    next_cursor: Cursor | None


class ProjectService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.projects = ProjectRepository(session)

    async def create(
        self, *, organization_id: uuid.UUID, created_by_id: uuid.UUID | None, data: ProjectCreate
    ) -> Project:
        project = await self.projects.add(
            Project(
                organization_id=organization_id,
                created_by_id=created_by_id,
                name=data.name,
                description=data.description,
            )
        )
        await self.session.commit()
        return project

    async def get(self, project_id: uuid.UUID, organization_id: uuid.UUID) -> Project:
        project = await self.projects.get_by_id_for_org(project_id, organization_id)
        if project is None:
            raise NotFoundError("Project not found")
        return project

    async def list(
        self,
        organization_id: uuid.UUID,
        *,
        name_contains: str | None = None,
        cursor: Cursor | None = None,
        limit: int = 20,
    ) -> ProjectPage:
        # Fetch one extra row to know whether another page exists, without a
        # separate count query.
        rows = await self.projects.list_for_org(
            organization_id, name_contains=name_contains, cursor=cursor, limit=limit + 1
        )
        has_more = len(rows) > limit
        items = rows[:limit]
        next_cursor = (
            Cursor(created_at=items[-1].created_at, id=items[-1].id) if has_more and items else None
        )
        return ProjectPage(items=items, next_cursor=next_cursor)

    async def update(
        self, project_id: uuid.UUID, organization_id: uuid.UUID, data: ProjectUpdate
    ) -> Project:
        project = await self.get(project_id, organization_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(project, field, value)
        await self.session.commit()
        # `updated_at` is server-computed (onupdate=func.now()); refresh so
        # the returned object reflects it instead of a stale/unloaded value.
        await self.session.refresh(project)
        return project

    async def delete(self, project_id: uuid.UUID, organization_id: uuid.UUID) -> None:
        project = await self.get(project_id, organization_id)
        await self.projects.delete(project)
        await self.session.commit()
