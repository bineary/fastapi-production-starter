import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


async def test_validation_error_has_consistent_field_level_shape(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "",  # too short
            "email": "not-an-email",
            "password": "short",  # too short
            "full_name": "Someone",
        },
    )
    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["type"] == "/problems/validation-error"
    assert body["status"] == 422
    assert body["trace_id"]

    fields = {e["field"] for e in body["errors"]}
    assert {"organization_name", "email", "password"} <= fields
    for error in body["errors"]:
        assert {"field", "message", "type"} <= error.keys()


async def test_unmatched_route_returns_problem_json_404(api_client: AsyncClient) -> None:
    response = await api_client.get("/api/v1/this-route-does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["status"] == 404


async def test_auth_rate_limit_returns_429_with_retry_after(api_client: AsyncClient) -> None:
    settings_limit = 5  # matches RATE_LIMIT_AUTH_REQUESTS default
    responses = [
        await api_client.post(
            "/api/v1/auth/login", data={"username": "nobody@example.com", "password": "wrong"}
        )
        for _ in range(settings_limit + 2)
    ]

    assert [r.status_code for r in responses[:settings_limit]] == [401] * settings_limit
    limited = responses[settings_limit:]
    assert all(r.status_code == 429 for r in limited)
    assert all(r.headers["content-type"] == "application/problem+json" for r in limited)
    assert all("Retry-After" in r.headers for r in limited)
