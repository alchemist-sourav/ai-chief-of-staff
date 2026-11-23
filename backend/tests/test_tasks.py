import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_task_crud_endpoints(client: AsyncClient):
    """Test full CRUD lifecycle for tasks via REST API."""
    # 1. Create Task
    task_payload = {
        "title": "Prepare Pitch Deck",
        "description": "Finalize slides 5 through 10 for investor presentation",
        "priority": "HIGH",
        "status": "TODO"
    }
    create_res = await client.post("/api/v1/tasks", json=task_payload)
    assert create_res.status_code == 201
    task_data = create_res.json()
    task_id = task_data["id"]
    assert task_data["title"] == "Prepare Pitch Deck"
    assert task_data["priority"] == "HIGH"

    # 2. List Tasks
    list_res = await client.get("/api/v1/tasks")
    assert list_res.status_code == 200
    tasks = list_res.json()
    assert len(tasks) >= 1
    assert any(t["id"] == task_id for t in tasks)

    # 3. Filter Tasks by Priority
    filter_res = await client.get("/api/v1/tasks?priority=HIGH")
    assert filter_res.status_code == 200
    filtered = filter_res.json()
    assert all(t["priority"] == "HIGH" for t in filtered)

    # 4. Update Task (toggle status to IN_PROGRESS)
    update_res = await client.patch(f"/api/v1/tasks/{task_id}", json={"status": "IN_PROGRESS"})
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["status"] == "IN_PROGRESS"

    # 5. Delete Task
    delete_res = await client.delete(f"/api/v1/tasks/{task_id}")
    assert delete_res.status_code == 204

    # 6. Verify Deleted
    get_res = await client.get(f"/api/v1/tasks/{task_id}")
    assert get_res.status_code == 404
