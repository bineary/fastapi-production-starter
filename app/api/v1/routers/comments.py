import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.v1.responses import FORBIDDEN, NOT_FOUND, UNAUTHORIZED, VALIDATION
from app.core.dependencies import DbSession, require_role
from app.models.enums import OrgRole
from app.models.user import User
from app.schemas.comment import CommentCreate, CommentRead
from app.services.comment_service import CommentService

router = APIRouter(
    prefix="/tasks/{task_id}/comments",
    tags=["comments"],
    responses={**UNAUTHORIZED, **VALIDATION, **NOT_FOUND},
)


def _service(db: DbSession) -> CommentService:
    return CommentService(db)


@router.post(
    "", response_model=CommentRead, status_code=status.HTTP_201_CREATED, summary="Add a comment"
)
async def create_comment(
    task_id: uuid.UUID,
    body: CommentCreate,
    current_user: Annotated[User, Depends(require_role(OrgRole.MEMBER))],
    db: DbSession,
) -> CommentRead:
    comment = await _service(db).create(
        task_id=task_id,
        organization_id=current_user.organization_id,
        author_id=current_user.id,
        data=body,
    )
    return CommentRead.model_validate(comment)


@router.get("", response_model=list[CommentRead], summary="List comments on a task")
async def list_comments(
    task_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(OrgRole.MEMBER))],
    db: DbSession,
) -> list[CommentRead]:
    comments = await _service(db).list_for_task(task_id, current_user.organization_id)
    return [CommentRead.model_validate(c) for c in comments]


@router.delete(
    "/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
    description="Allowed for the comment's author, or for the `admin` role or higher.",
    responses={**FORBIDDEN},
)
async def delete_comment(
    task_id: uuid.UUID,
    comment_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_role(OrgRole.MEMBER))],
    db: DbSession,
) -> None:
    await _service(db).delete(
        task_id=task_id,
        comment_id=comment_id,
        organization_id=current_user.organization_id,
        requesting_user=current_user,
    )
