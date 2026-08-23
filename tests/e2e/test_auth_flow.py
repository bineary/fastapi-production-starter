import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


async def _register(client: AsyncClient, *, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Acme Inc.",
            "email": email,
            "password": "a-strong-password-123",
            "full_name": "Ada Lovelace",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _login(client: AsyncClient, *, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "a-strong-password-123"},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_register_then_login_then_me(api_client: AsyncClient) -> None:
    user = await _register(api_client, email="owner@acme.example.com")
    assert user["email"] == "owner@acme.example.com"
    assert user["role"] == "owner"

    tokens = await _login(api_client, email="owner@acme.example.com")
    assert tokens["token_type"] == "bearer"

    me = await api_client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == "owner@acme.example.com"


async def test_login_with_wrong_password_is_rejected(api_client: AsyncClient) -> None:
    await _register(api_client, email="user@wrongpw.example.com")
    response = await api_client.post(
        "/api/v1/auth/login", data={"username": "user@wrongpw.example.com", "password": "nope"}
    )
    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"


async def test_refresh_rotates_the_token(api_client: AsyncClient) -> None:
    await _register(api_client, email="rotate@acme.example.com")
    tokens = await _login(api_client, email="rotate@acme.example.com")

    refreshed = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200
    new_tokens = refreshed.json()
    # Only refresh-token uniqueness is the security property here — two access
    # tokens issued in the same second are legitimately byte-identical JWTs
    # (same claims, second-precision iat/exp), which is fine since they're stateless.
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


async def test_reusing_a_rotated_refresh_token_revokes_the_whole_session(
    api_client: AsyncClient,
) -> None:
    await _register(api_client, email="reuse@acme.example.com")
    original = await _login(api_client, email="reuse@acme.example.com")

    first_refresh = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
    )
    assert first_refresh.status_code == 200
    rotated_tokens = first_refresh.json()

    # Reusing the now-rotated-out original token is theft, not a retry.
    reuse_attempt = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": original["refresh_token"]}
    )
    assert reuse_attempt.status_code == 401

    # The whole family — including the token issued by the legitimate
    # rotation above — must now be dead too.
    legitimate_followup = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated_tokens["refresh_token"]}
    )
    assert legitimate_followup.status_code == 401


async def test_logout_revokes_the_refresh_token(api_client: AsyncClient) -> None:
    await _register(api_client, email="logout@acme.example.com")
    tokens = await _login(api_client, email="logout@acme.example.com")

    logout_response = await api_client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    assert logout_response.status_code == 204

    refresh_after_logout = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_after_logout.status_code == 401


async def test_change_password_revokes_existing_sessions(api_client: AsyncClient) -> None:
    await _register(api_client, email="changepw@acme.example.com")
    tokens = await _login(api_client, email="changepw@acme.example.com")

    change_response = await api_client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "a-strong-password-123", "new_password": "an-even-stronger-pw"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert change_response.status_code == 204

    stale_refresh = await api_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert stale_refresh.status_code == 401

    new_login = await api_client.post(
        "/api/v1/auth/login",
        data={"username": "changepw@acme.example.com", "password": "an-even-stronger-pw"},
    )
    assert new_login.status_code == 200


async def test_me_without_token_is_unauthorized(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_registering_the_same_email_twice_conflicts(api_client: AsyncClient) -> None:
    await _register(api_client, email="dupe@acme.example.com")
    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Someone Else Inc.",
            "email": "dupe@acme.example.com",
            "password": "a-strong-password-123",
            "full_name": "Someone Else",
        },
    )
    assert response.status_code == 409
