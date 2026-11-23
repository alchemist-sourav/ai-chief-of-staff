import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_health_endpoint(client: AsyncClient):
    """Verify GET /api/health returns 200 with database and groq statuses."""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "database_connected" in data
    assert "groq_configured" in data
    assert data["service"] == "AI Chief of Staff"


@pytest.mark.asyncio
async def test_v1_health_endpoint(client: AsyncClient):
    """Verify GET /api/v1/health returns 200."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "0.2.0"
    assert data["default_model"] == "openai/gpt-oss-120b"
