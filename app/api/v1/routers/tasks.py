import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.v1.params import parse_cursor
from app.api.v1.responses import FORBIDDEN, NOT_FOUND, UNAUTHORIZED, VALIDATION
from app.core.dependencies import DbSession, require_role
from app.models.enums import OrgRole, TaskPriority, TaskStatus
from app.models.user import User
from app.schemas.pagination import Page
from app.schemas.task import TaskCreate, TaskRead, TaskUpdate
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["tasks"], responses={**UNAUTHORIZED, **VALIDATION})


def _service(db: DbSession) -> TaskService:
    return TaskService(db)


@router.post(
    "",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
    description=(
        "Requires the `member` role or higher. `assignee_id`, if given, must belong "
        "to the same organization."
    ),
    responses={**NOT_FOUND},
)
async def create_task(
    body: TaskCreate,
    current_user: Annotated[User, Depends(require_role(OrgRole.MEMBER))],
    db: DbSession,
) -> TaskRead:
    task = await _service(db).create(
        organization_id=current_user.organization_id, created_by_id=current_user.id, data=body
    )
    return TaskRead.model_validate(task)


@router.get("", response_model=Page[TaskRead], summary="List tasks (paginated, filterable)")
async def list_tasks(
    current_user: Annotated[User, Depends(require_role(OrgRole.MEMBER))],
    db: DbSession,
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page"),
    limit: int = Query(default=20, ge=1, le=100),
    project_id: uuid.UUID | None = None,
    status_filter: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = None,
    assignee_id: uuid.UUID | None = None,
    title: str | None = Query(default=None, description="Case-insensitive substring filter"),
) -> Page[TaskRead]:
    page = await _service(db).list(
        current_user.organization_id,
        project_id=project_id,
        status=status_filter,
        priority=priority,
        assignee_id=assignee_id,
        title_contains=title,
        cursor=parse_cursor(cursor),
        limit=limit,
    )
    return Page(
        items=[TaskRead.model_validate(t) for t in page.items],
        next_cursor=page.next_cursor.encode() if page.next_cursor else None,
    )


@router.get(
    "/{task_id}", response_model=TaskRead, summary="Get a task by id", responses={**NOT_FOUND}
)
async def get_task(
    task_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(OrgRole.MEMBER))],
    db: DbSession,
) -> TaskRead:
    task = await _service(db).get(task_id, current_user.organization_id)
    return TaskRead.model_validate(task)


@router.patch(
    "/{task_id}",
    response_model=TaskRead,
    summary="Partially update a task",
    description="Requires the `member` role or higher. Only fields present in the body change.",
    responses={**NOT_FOUND},
)
async def update_task(
    task_id: uuid.UUID,
    body: TaskUpdate,
    current_user: Annotated[User, Depends(require_role(OrgRole.MEMBER))],
    db: DbSession,
) -> TaskRead:
    task = await _service(db).update(task_id, current_user.organization_id, body)
    return TaskRead.model_validate(task)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    description="Requires the `admin` role or higher.",
    responses={**NOT_FOUND, **FORBIDDEN},
)
async def delete_task(
    task_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(OrgRole.ADMIN))],
    db: DbSession,
) -> None:
    await _service(db).delete(task_id, current_user.organization_id)
