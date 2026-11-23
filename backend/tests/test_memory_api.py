import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_memory_api_endpoints(client: AsyncClient):
    """Test creating and retrieving memories through the REST API."""
    # 1. Create Memory
    payload = {
        "category": "WORK_STYLE",
        "key": "meeting_duration",
        "value": "Prefer 25-minute meetings instead of 30 minutes",
    }
    create_res = await client.post("/api/v1/memory", json=payload)
    assert create_res.status_code == 200
    data = create_res.json()
    assert data["key"] == "meeting_duration"
    assert data["category"] == "WORK_STYLE"

    # 2. List Memories
    list_res = await client.get("/api/v1/memory")
    assert list_res.status_code == 200
    memories = list_res.json()
    assert len(memories) >= 1
    assert any(m["key"] == "meeting_duration" for m in memories)

    # 3. Filter Memories by Category
    filter_res = await client.get("/api/v1/memory?category=WORK_STYLE")
    assert filter_res.status_code == 200
    filtered = filter_res.json()
    assert all(m["category"] == "WORK_STYLE" for m in filtered)
