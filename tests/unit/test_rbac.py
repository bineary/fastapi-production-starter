import uuid

import pytest

from app.core.dependencies import require_role
from app.core.exceptions import ForbiddenError
from app.models.enums import OrgRole
from app.models.user import User

pytestmark = pytest.mark.unit


def _user(role: OrgRole) -> User:
    return User(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        email="user@example.com",
        hashed_password="x",
        full_name="Test User",
        role=role,
        is_active=True,
    )


@pytest.mark.parametrize(
    ("user_role", "minimum_role", "allowed"),
    [
        (OrgRole.OWNER, OrgRole.MEMBER, True),
        (OrgRole.OWNER, OrgRole.ADMIN, True),
        (OrgRole.OWNER, OrgRole.OWNER, True),
        (OrgRole.ADMIN, OrgRole.MEMBER, True),
        (OrgRole.ADMIN, OrgRole.ADMIN, True),
        (OrgRole.ADMIN, OrgRole.OWNER, False),
        (OrgRole.MEMBER, OrgRole.MEMBER, True),
        (OrgRole.MEMBER, OrgRole.ADMIN, False),
        (OrgRole.MEMBER, OrgRole.OWNER, False),
    ],
)
def test_require_role_permission_matrix(
    user_role: OrgRole, minimum_role: OrgRole, allowed: bool
) -> None:
    check = require_role(minimum_role)
    user = _user(user_role)

    if allowed:
        assert check(user) is user
    else:
        with pytest.raises(ForbiddenError):
            check(user)
