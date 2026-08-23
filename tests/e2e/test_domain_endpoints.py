import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.models.enums import OrgRole
from app.models.user import User
from app.repositories.user_repository import UserRepository

pytestmark = pytest.mark.e2e


async def _register(client: AsyncClient, *, email: str, org_name: str = "Acme Inc.") -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": org_name,
            "email": email,
            "password": "a-strong-password-123",
            "full_name": "Test Owner",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role,
        settings=get_settings(),
    )
    return {"Authorization": f"Bearer {token}"}


async def _add_user_with_role(
    db_session: AsyncSession, *, organization_id: uuid.UUID, role: OrgRole, email: str
) -> User:
    """Bypasses the API — there's no invite endpoint in scope, and this is
    fixture setup for RBAC tests, not a test of registration itself."""
    user = await UserRepository(db_session).add(
        User(
            organization_id=organization_id,
            email=email,
            hashed_password=hash_password("irrelevant-for-these-tests"),
            full_name="Fixture User",
            role=role,
            is_active=True,
        )
    )
    await db_session.commit()
    return user


async def test_project_rbac_matrix(api_client: AsyncClient, db_session: AsyncSession) -> None:
    owner_data = await _register(api_client, email="owner@project-rbac.example.com")
    org_id = uuid.UUID(owner_data["organization_id"])
    owner = await UserRepository(db_session).get_by_id(uuid.UUID(owner_data["id"]))
    assert owner is not None

    member = await _add_user_with_role(
        db_session,
        organization_id=org_id,
        role=OrgRole.MEMBER,
        email="member@project-rbac.example.com",
    )
    admin = await _add_user_with_role(
        db_session,
        organization_id=org_id,
        role=OrgRole.ADMIN,
        email="admin@project-rbac.example.com",
    )

    # A member cannot create a project.
    member_create = await api_client.post(
        "/api/v1/projects", json={"name": "Members can't make this"}, headers=_auth_headers(member)
    )
    assert member_create.status_code == 403

    # An admin can.
    admin_create = await api_client.post(
        "/api/v1/projects", json={"name": "Admin's project"}, headers=_auth_headers(admin)
    )
    assert admin_create.status_code == 201
    project = admin_create.json()

    # A member can read it.
    member_get = await api_client.get(
        f"/api/v1/projects/{project['id']}", headers=_auth_headers(member)
    )
    assert member_get.status_code == 200

    # A member cannot delete it; an admin can.
    member_delete = await api_client.delete(
        f"/api/v1/projects/{project['id']}", headers=_auth_headers(member)
    )
    assert member_delete.status_code == 403

    admin_delete = await api_client.delete(
        f"/api/v1/projects/{project['id']}", headers=_auth_headers(admin)
    )
    assert admin_delete.status_code == 204


async def test_tenancy_isolation_across_orgs(api_client: AsyncClient) -> None:
    org_a_owner = await _register(api_client, email="owner@org-a.example.com", org_name="Org A")
    org_b_owner = await _register(api_client, email="owner@org-b.example.com", org_name="Org B")

    org_a_headers = {
        "Authorization": f"Bearer {(await _login(api_client, 'owner@org-a.example.com'))}"
    }
    org_b_headers = {
        "Authorization": f"Bearer {(await _login(api_client, 'owner@org-b.example.com'))}"
    }
    assert org_a_owner["organization_id"] != org_b_owner["organization_id"]

    create_response = await api_client.post(
        "/api/v1/projects", json={"name": "Org A's secret project"}, headers=org_a_headers
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    # Org B must not be able to see org A's project at all — 404, not 403,
    # so existence of another tenant's data is never revealed.
    cross_org_get = await api_client.get(f"/api/v1/projects/{project_id}", headers=org_b_headers)
    assert cross_org_get.status_code == 404

    own_org_get = await api_client.get(f"/api/v1/projects/{project_id}", headers=org_a_headers)
    assert own_org_get.status_code == 200

    listing = await api_client.get("/api/v1/projects", headers=org_b_headers)
    assert project_id not in {p["id"] for p in listing.json()["items"]}


async def _login(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "a-strong-password-123"}
    )
    assert response.status_code == 200
    access_token: str = response.json()["access_token"]
    return access_token


async def test_task_patch_only_changes_provided_fields(api_client: AsyncClient) -> None:
    owner_data = await _register(api_client, email="owner@patch-test.example.com")
    headers = {
        "Authorization": f"Bearer {await _login(api_client, 'owner@patch-test.example.com')}"
    }

    project = (
        await api_client.post("/api/v1/projects", json={"name": "Patch Co"}, headers=headers)
    ).json()
    task = (
        await api_client.post(
            "/api/v1/tasks",
            json={"project_id": project["id"], "title": "Original title", "priority": "low"},
            headers=headers,
        )
    ).json()

    patched = await api_client.patch(
        f"/api/v1/tasks/{task['id']}", json={"status": "in_progress"}, headers=headers
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["status"] == "in_progress"
    assert body["title"] == "Original title"  # untouched
    assert body["priority"] == "low"  # untouched

    assert owner_data["organization_id"] == body["organization_id"]


async def test_task_assignee_must_belong_to_same_org(api_client: AsyncClient) -> None:
    await _register(api_client, email="owner@assignee-test.example.com")
    headers = {
        "Authorization": f"Bearer {await _login(api_client, 'owner@assignee-test.example.com')}"
    }
    other_org_owner = await _register(
        api_client, email="owner@other-org.example.com", org_name="Other Org"
    )

    project = (
        await api_client.post("/api/v1/projects", json={"name": "Assignment Co"}, headers=headers)
    ).json()

    response = await api_client.post(
        "/api/v1/tasks",
        json={
            "project_id": project["id"],
            "title": "Cross-org assignment attempt",
            "assignee_id": other_org_owner["id"],
        },
        headers=headers,
    )
    assert response.status_code == 422


async def test_task_list_filters_and_paginates(api_client: AsyncClient) -> None:
    await _register(api_client, email="owner@list-test.example.com")
    headers = {"Authorization": f"Bearer {await _login(api_client, 'owner@list-test.example.com')}"}

    project = (
        await api_client.post("/api/v1/projects", json={"name": "List Co"}, headers=headers)
    ).json()

    for i in range(5):
        await api_client.post(
            "/api/v1/tasks",
            json={
                "project_id": project["id"],
                "title": f"Task {i}",
                "status": "done" if i == 0 else "todo",
            },
            headers=headers,
        )

    todo_only = await api_client.get(
        "/api/v1/tasks", params={"status": "todo", "project_id": project["id"]}, headers=headers
    )
    assert todo_only.status_code == 200
    assert len(todo_only.json()["items"]) == 4

    first_page = await api_client.get(
        "/api/v1/tasks", params={"project_id": project["id"], "limit": 2}, headers=headers
    )
    assert len(first_page.json()["items"]) == 2
    assert first_page.json()["next_cursor"] is not None

    second_page = await api_client.get(
        "/api/v1/tasks",
        params={
            "project_id": project["id"],
            "limit": 2,
            "cursor": first_page.json()["next_cursor"],
        },
        headers=headers,
    )
    assert len(second_page.json()["items"]) == 2
    first_ids = {t["id"] for t in first_page.json()["items"]}
    second_ids = {t["id"] for t in second_page.json()["items"]}
    assert first_ids.isdisjoint(second_ids)


async def test_comment_delete_permissions(
    api_client: AsyncClient, db_session: AsyncSession
) -> None:
    owner_data = await _register(api_client, email="owner@comment-test.example.com")
    org_id = uuid.UUID(owner_data["organization_id"])
    owner_headers = {
        "Authorization": f"Bearer {await _login(api_client, 'owner@comment-test.example.com')}"
    }

    member_a = await _add_user_with_role(
        db_session, organization_id=org_id, role=OrgRole.MEMBER, email="a@comment-test.example.com"
    )
    member_b = await _add_user_with_role(
        db_session, organization_id=org_id, role=OrgRole.MEMBER, email="b@comment-test.example.com"
    )

    project = (
        await api_client.post(
            "/api/v1/projects", json={"name": "Comment Co"}, headers=owner_headers
        )
    ).json()
    task = (
        await api_client.post(
            "/api/v1/tasks",
            json={"project_id": project["id"], "title": "Discuss this"},
            headers=owner_headers,
        )
    ).json()

    comment = (
        await api_client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            json={"body": "My opinion"},
            headers=_auth_headers(member_a),
        )
    ).json()

    # A different, non-admin member can't delete someone else's comment.
    forbidden = await api_client.delete(
        f"/api/v1/tasks/{task['id']}/comments/{comment['id']}", headers=_auth_headers(member_b)
    )
    assert forbidden.status_code == 403

    # The author can.
    allowed = await api_client.delete(
        f"/api/v1/tasks/{task['id']}/comments/{comment['id']}", headers=_auth_headers(member_a)
    )
    assert allowed.status_code == 204
