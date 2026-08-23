import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.e2e


async def test_health_ready_reports_db_and_redis_up(api_client: AsyncClient) -> None:
    response = await api_client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body == {"status": "ready", "checks": {"database": True, "redis": True}}


async def test_metrics_endpoint_is_exposed(api_client: AsyncClient) -> None:
    response = await api_client.get("/metrics")
    assert response.status_code == 200
    assert b"python_gc_objects_collected_total" in response.content
