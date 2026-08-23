import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Cursor
from app.models.comment import Comment
from app.models.enums import OrgRole, TaskPriority, TaskStatus
from app.models.organization import Organization
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.repositories.comment_repository import CommentRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_repository import UserRepository

pytestmark = pytest.mark.integration


async def _make_org(session: AsyncSession, slug: str) -> Organization:
    org = await OrganizationRepository(session).add(Organization(name=slug, slug=slug))
    return org


async def _make_user(session: AsyncSession, org: Organization, email: str) -> User:
    user = await UserRepository(session).add(
        User(
            organization_id=org.id,
            email=email,
            hashed_password="not-a-real-hash",
            full_name="Test User",
            role=OrgRole.MEMBER,
        )
    )
    return user


async def test_full_hierarchy_can_be_created(db_session: AsyncSession) -> None:
    org = await _make_org(db_session, "acme")
    user = await _make_user(db_session, org, "owner@acme.test")

    project = await ProjectRepository(db_session).add(
        Project(organization_id=org.id, name="Launch", created_by_id=user.id)
    )
    task = await TaskRepository(db_session).add(
        Task(
            organization_id=org.id,
            project_id=project.id,
            title="Ship it",
            created_by_id=user.id,
            assignee_id=user.id,
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
        )
    )
    comment = await CommentRepository(db_session).add(
        Comment(organization_id=org.id, task_id=task.id, author_id=user.id, body="LGTM")
    )

    fetched_task = await TaskRepository(db_session).get_by_id_for_org(task.id, org.id)
    assert fetched_task is not None
    assert fetched_task.title == "Ship it"
    assert fetched_task.assignee_id == user.id

    task_comments = await CommentRepository(db_session).list_for_task(task.id, org.id)
    assert [c.id for c in task_comments] == [comment.id]


async def test_tenancy_isolation_blocks_cross_org_reads(db_session: AsyncSession) -> None:
    org_a = await _make_org(db_session, "org-a")
    org_b = await _make_org(db_session, "org-b")
    user_a = await _make_user(db_session, org_a, "user@org-a.test")

    project_a = await ProjectRepository(db_session).add(
        Project(organization_id=org_a.id, name="A's project", created_by_id=user_a.id)
    )
    task_a = await TaskRepository(db_session).add(
        Task(organization_id=org_a.id, project_id=project_a.id, title="A's task")
    )

    # Org B must not be able to read org A's task through the org-scoped lookup.
    assert await TaskRepository(db_session).get_by_id_for_org(task_a.id, org_b.id) is None
    assert await TaskRepository(db_session).get_by_id_for_org(task_a.id, org_a.id) is not None

    # And a list scoped to org B must never include org A's rows.
    org_b_tasks = await TaskRepository(db_session).list_for_org(org_b.id)
    assert task_a.id not in {t.id for t in org_b_tasks}


async def test_task_list_filters_by_status_and_assignee(db_session: AsyncSession) -> None:
    org = await _make_org(db_session, "filter-co")
    user = await _make_user(db_session, org, "assignee@filter-co.test")
    project = await ProjectRepository(db_session).add(
        Project(organization_id=org.id, name="Filters")
    )
    repo = TaskRepository(db_session)
    await repo.add(
        Task(
            organization_id=org.id,
            project_id=project.id,
            title="Done task",
            status=TaskStatus.DONE,
            assignee_id=user.id,
        )
    )
    todo_task = await repo.add(
        Task(
            organization_id=org.id,
            project_id=project.id,
            title="Todo task",
            status=TaskStatus.TODO,
            assignee_id=user.id,
        )
    )
    await repo.add(Task(organization_id=org.id, project_id=project.id, title="Unassigned todo"))

    results = await repo.list_for_org(org.id, status=TaskStatus.TODO, assignee_id=user.id)

    assert [t.id for t in results] == [todo_task.id]


async def test_project_list_cursor_pagination_walks_all_rows_without_overlap(
    db_session: AsyncSession,
) -> None:
    org = await _make_org(db_session, "paginate-co")
    repo = ProjectRepository(db_session)
    created = [
        await repo.add(Project(organization_id=org.id, name=f"Project {i}")) for i in range(5)
    ]

    seen: list[uuid.UUID] = []
    cursor: Cursor | None = None
    for _ in range(10):  # bounded loop guard against an infinite-pagination bug
        page = await repo.list_for_org(org.id, cursor=cursor, limit=2)
        if not page:
            break
        seen.extend(p.id for p in page)
        cursor = Cursor(created_at=page[-1].created_at, id=page[-1].id)

    assert len(seen) == len(created)
    assert len(set(seen)) == len(created)  # no duplicates across pages
