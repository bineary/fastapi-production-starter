import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.organization import Organization
from app.repositories.organization_repository import OrganizationRepository
from app.schemas.comment import CommentCreate
from app.schemas.project import ProjectCreate
from app.schemas.task import TaskCreate
from app.services.comment_service import CommentService
from app.services.project_service import ProjectService
from app.services.task_service import TaskService

pytestmark = pytest.mark.integration


async def _make_org(db_session: AsyncSession, slug: str) -> Organization:
    return await OrganizationRepository(db_session).add(Organization(name=slug, slug=slug))


async def test_project_get_missing_raises_not_found(db_session: AsyncSession) -> None:
    org = await _make_org(db_session, "svc-project-co")
    with pytest.raises(NotFoundError):
        await ProjectService(db_session).get(uuid.uuid4(), org.id)


async def test_project_list_filters_by_name(db_session: AsyncSession) -> None:
    org = await _make_org(db_session, "svc-project-filter-co")
    service = ProjectService(db_session)
    await service.create(
        organization_id=org.id, created_by_id=None, data=ProjectCreate(name="Website Relaunch")
    )
    await service.create(
        organization_id=org.id, created_by_id=None, data=ProjectCreate(name="Mobile App")
    )

    page = await service.list(org.id, name_contains="website")
    assert [p.name for p in page.items] == ["Website Relaunch"]


async def test_task_get_missing_raises_not_found(db_session: AsyncSession) -> None:
    org = await _make_org(db_session, "svc-task-co")
    with pytest.raises(NotFoundError):
        await TaskService(db_session).get(uuid.uuid4(), org.id)


async def test_task_create_for_missing_project_raises_not_found(db_session: AsyncSession) -> None:
    org = await _make_org(db_session, "svc-task-noproject-co")
    with pytest.raises(NotFoundError):
        await TaskService(db_session).create(
            organization_id=org.id,
            created_by_id=None,
            data=TaskCreate(project_id=uuid.uuid4(), title="Orphan task"),
        )


async def test_task_delete_removes_it(db_session: AsyncSession) -> None:
    org = await _make_org(db_session, "svc-task-delete-co")
    project_service = ProjectService(db_session)
    task_service = TaskService(db_session)
    project = await project_service.create(
        organization_id=org.id, created_by_id=None, data=ProjectCreate(name="Deletable")
    )
    task = await task_service.create(
        organization_id=org.id,
        created_by_id=None,
        data=TaskCreate(project_id=project.id, title="Delete me"),
    )

    await task_service.delete(task.id, org.id)

    with pytest.raises(NotFoundError):
        await task_service.get(task.id, org.id)


async def test_task_list_filters_by_title(db_session: AsyncSession) -> None:
    org = await _make_org(db_session, "svc-task-titlefilter-co")
    project_service = ProjectService(db_session)
    task_service = TaskService(db_session)
    project = await project_service.create(
        organization_id=org.id, created_by_id=None, data=ProjectCreate(name="Title Filters")
    )
    await task_service.create(
        organization_id=org.id,
        created_by_id=None,
        data=TaskCreate(project_id=project.id, title="Fix the login bug"),
    )
    await task_service.create(
        organization_id=org.id,
        created_by_id=None,
        data=TaskCreate(project_id=project.id, title="Write docs"),
    )

    page = await task_service.list(org.id, title_contains="login")
    assert [t.title for t in page.items] == ["Fix the login bug"]


async def test_comment_list_for_missing_task_raises_not_found(db_session: AsyncSession) -> None:
    org = await _make_org(db_session, "svc-comment-co")
    with pytest.raises(NotFoundError):
        await CommentService(db_session).list_for_task(uuid.uuid4(), org.id)


async def test_comment_create_for_missing_task_raises_not_found(db_session: AsyncSession) -> None:
    org = await _make_org(db_session, "svc-comment-noTask-co")
    with pytest.raises(NotFoundError):
        await CommentService(db_session).create(
            task_id=uuid.uuid4(),
            organization_id=org.id,
            author_id=uuid.uuid4(),
            data=CommentCreate(body="Orphan comment"),
        )
