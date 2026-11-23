import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.task import Task
from app.models.approval import ApprovalRequest, ApprovalStatus
from app.core.security import create_access_token
from app.services.approval_service import ApprovalService


@pytest.mark.asyncio
async def test_list_approvals_with_user_isolation(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """1. Test listing approvals enforces user isolation."""
    # User A approval
    appr_a = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary="User A task deletion",
        proposed_payload={"task_id": "1"},
    )

    # User B approval
    user_b = User(id="usr-b-api-001", email="user_b@homingo.ai", is_active=True)
    db_session.add(user_b)
    await db_session.commit()

    appr_b = await ApprovalService.create_request(
        session=db_session,
        user_id=user_b.id,
        action_type="DELETE_TASK",
        summary="User B task deletion",
        proposed_payload={"task_id": "2"},
    )

    # Request as User A
    res_a = await client.get("/api/v1/approvals")
    assert res_a.status_code == 200
    approvals_a = res_a.json()
    assert len(approvals_a) == 1
    assert approvals_a[0]["id"] == appr_a.id

    # Request as User B
    token_b = create_access_token(user_b.id, user_b.email)
    res_b = await client.get("/api/v1/approvals", headers={"Authorization": f"Bearer {token_b}"})
    assert res_b.status_code == 200
    approvals_b = res_b.json()
    assert len(approvals_b) == 1
    assert approvals_b[0]["id"] == appr_b.id


@pytest.mark.asyncio
async def test_get_individual_approval(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """2. Test retrieving a single approval request by ID."""
    appr = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="PROPOSE_EXTERNAL_ACTION",
        summary="Send invitation",
        proposed_payload={"to": "exec@company.com"},
    )

    res = await client.get(f"/api/v1/approvals/{appr.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == appr.id
    assert data["action_type"] == "PROPOSE_EXTERNAL_ACTION"
    assert data["status"] == "PENDING"


@pytest.mark.asyncio
async def test_approve_and_execute_task_deletion_api(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """3. Test approving and executing a deletion request via API."""
    task = Task(user_id=test_user.id, title="Task to delete via API")
    db_session.add(task)
    await db_session.commit()

    appr = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary="Delete task via API",
        proposed_payload={"task_id": task.id},
    )

    res = await client.post(
        f"/api/v1/approvals/{appr.id}/approve",
        json={"comment": "Approved by executive."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "EXECUTED"
    assert data["result_data"]["deleted_task_id"] == task.id

    # Verify task was deleted from DB
    check_task = await db_session.get(Task, task.id)
    assert check_task is None

    # Verify approval state in DB
    await db_session.refresh(appr)
    assert appr.status == "EXECUTED"
    assert appr.user_comment == "Approved by executive."


@pytest.mark.asyncio
async def test_reject_approval_api(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """4. Test rejecting an approval request via API."""
    task = Task(user_id=test_user.id, title="Task not to be deleted")
    db_session.add(task)
    await db_session.commit()

    appr = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary="Delete rejected task",
        proposed_payload={"task_id": task.id},
    )

    res = await client.post(
        f"/api/v1/approvals/{appr.id}/reject",
        json={"comment": "Rejected because task is needed."},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "REJECTED"
    assert data["user_comment"] == "Rejected because task is needed."

    # Verify task was NOT deleted
    check_task = await db_session.get(Task, task.id)
    assert check_task is not None


@pytest.mark.asyncio
async def test_unauthenticated_approval_denial(unauth_client: AsyncClient):
    """5. Test unauthenticated requests are rejected with 401."""
    res_list = await unauth_client.get("/api/v1/approvals")
    assert res_list.status_code == 401

    res_get = await unauth_client.get("/api/v1/approvals/any-id")
    assert res_get.status_code == 401

    res_appr = await unauth_client.post("/api/v1/approvals/any-id/approve")
    assert res_appr.status_code == 401

    res_rej = await unauth_client.post("/api/v1/approvals/any-id/reject")
    assert res_rej.status_code == 401


@pytest.mark.asyncio
async def test_cross_user_approval_access_denial(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """6. Test User B cannot access or modify User A's approval requests."""
    appr_a = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary="User A confidential approval",
        proposed_payload={"task_id": "test_id"},
    )

    user_b = User(id="user-b-evil", email="user_b_evil@homingo.ai", is_active=True)
    db_session.add(user_b)
    await db_session.commit()
    token_b = create_access_token(user_b.id, user_b.email)
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B attempts GET User A's approval -> 404
    get_res = await client.get(f"/api/v1/approvals/{appr_a.id}", headers=headers_b)
    assert get_res.status_code == 404

    # User B attempts APPROVE User A's approval -> 404
    appr_res = await client.post(f"/api/v1/approvals/{appr_a.id}/approve", headers=headers_b)
    assert appr_res.status_code == 404

    # User B attempts REJECT User A's approval -> 404
    rej_res = await client.post(f"/api/v1/approvals/{appr_a.id}/reject", headers=headers_b)
    assert rej_res.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_approval_prevention_api(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """7. Test duplicate approve calls are rejected with 400."""
    appr = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="PROPOSE_EXTERNAL_ACTION",
        summary="Action proposal",
        proposed_payload={"key": "val"},
    )

    # First approve succeeds
    res1 = await client.post(f"/api/v1/approvals/{appr.id}/approve")
    assert res1.status_code == 200

    # Second approve fails with 400
    res2 = await client.post(f"/api/v1/approvals/{appr.id}/approve")
    assert res2.status_code == 400
    assert "already been executed" in res2.json()["detail"] or "Must be 'PENDING'" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_approval_id_handling(client: AsyncClient):
    """8. Test 404 handling on non-existent approval ID."""
    res = await client.get("/api/v1/approvals/non-existent-uuid-999")
    assert res.status_code == 404
    assert res.json()["detail"] == "Approval request not found."


@pytest.mark.asyncio
async def test_tampered_approval_rejection_api(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """9. Test cryptographic tamper rejection returns 409 or 400."""
    appr = await ApprovalService.create_request(
        session=db_session,
        user_id=test_user.id,
        action_type="DELETE_TASK",
        summary="Tampered task",
        proposed_payload={"task_id": "legit_task"},
    )

    # Out-of-band tampering of payload
    appr.proposed_payload = {"task_id": "victim_task"}
    await db_session.commit()

    res = await client.post(f"/api/v1/approvals/{appr.id}/approve")
    assert res.status_code == 409
    assert "tamper" in res.json()["detail"].lower()
