import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.v1.params import parse_cursor
from app.api.v1.responses import FORBIDDEN, NOT_FOUND, UNAUTHORIZED, VALIDATION
from app.core.dependencies import DbSession, require_role
from app.models.enums import OrgRole
from app.models.user import User
from app.schemas.pagination import Page
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"], responses={**UNAUTHORIZED, **VALIDATION})


def _service(db: DbSession) -> ProjectService:
    return ProjectService(db)


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a project",
    description="Requires the `admin` role or higher.",
    responses={**FORBIDDEN},
)
async def create_project(
    body: ProjectCreate,
    current_user: Annotated[User, Depends(require_role(OrgRole.ADMIN))],
    db: DbSession,
) -> ProjectRead:
    project = await _service(db).create(
        organization_id=current_user.organization_id, created_by_id=current_user.id, data=body
    )
    return ProjectRead.model_validate(project)


@router.get("", response_model=Page[ProjectRead], summary="List projects (cursor paginated)")
async def list_projects(
    current_user: Annotated[User, Depends(require_role(OrgRole.MEMBER))],
    db: DbSession,
    cursor: str | None = Query(default=None, description="Opaque cursor from a previous page"),
    limit: int = Query(default=20, ge=1, le=100),
    name: str | None = Query(default=None, description="Case-insensitive substring filter"),
) -> Page[ProjectRead]:
    page = await _service(db).list(
        current_user.organization_id, name_contains=name, cursor=parse_cursor(cursor), limit=limit
    )
    return Page(
        items=[ProjectRead.model_validate(p) for p in page.items],
        next_cursor=page.next_cursor.encode() if page.next_cursor else None,
    )


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Get a project by id",
    responses={**NOT_FOUND},
)
async def get_project(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(OrgRole.MEMBER))],
    db: DbSession,
) -> ProjectRead:
    project = await _service(db).get(project_id, current_user.organization_id)
    return ProjectRead.model_validate(project)


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    summary="Partially update a project",
    description="Requires the `admin` role or higher. Only fields present in the body change.",
    responses={**NOT_FOUND, **FORBIDDEN},
)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    current_user: Annotated[User, Depends(require_role(OrgRole.ADMIN))],
    db: DbSession,
) -> ProjectRead:
    project = await _service(db).update(project_id, current_user.organization_id, body)
    return ProjectRead.model_validate(project)


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
    description="Requires the `admin` role or higher. Cascades to the project's tasks/comments.",
    responses={**NOT_FOUND, **FORBIDDEN},
)
async def delete_project(
    project_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(OrgRole.ADMIN))],
    db: DbSession,
) -> None:
    await _service(db).delete(project_id, current_user.organization_id)
