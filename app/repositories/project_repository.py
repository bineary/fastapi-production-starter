import uuid

from sqlalchemy import Select, select, tuple_

from app.core.pagination import Cursor
from app.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model = Project

    async def get_by_id_for_org(
        self, project_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Project | None:
        result = await self.session.execute(
            select(Project).where(
                Project.id == project_id, Project.organization_id == organization_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_org(
        self,
        organization_id: uuid.UUID,
        *,
        name_contains: str | None = None,
        cursor: Cursor | None = None,
        limit: int = 20,
    ) -> list[Project]:
        stmt: Select[tuple[Project]] = select(Project).where(
            Project.organization_id == organization_id
        )

        if name_contains:
            stmt = stmt.where(Project.name.ilike(f"%{name_contains}%"))

        if cursor is not None:
            stmt = stmt.where(
                tuple_(Project.created_at, Project.id) < (cursor.created_at, cursor.id)
            )

        stmt = stmt.order_by(Project.created_at.desc(), Project.id.desc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
