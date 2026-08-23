from app.models.enums import OrgRole

ROLE_RANK: dict[OrgRole, int] = {OrgRole.MEMBER: 0, OrgRole.ADMIN: 1, OrgRole.OWNER: 2}


def role_at_least(role: OrgRole, minimum_role: OrgRole) -> bool:
    return ROLE_RANK[role] >= ROLE_RANK[minimum_role]
