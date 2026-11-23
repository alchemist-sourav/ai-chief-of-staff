import logging
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalRequest, ApprovalStatus, compute_canonical_payload_hash
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.task_service import TaskService
from app.services.tools.base import BaseTool, ToolResult, ToolSecurityLevel

logger = logging.getLogger("ai_chief_of_staff.tools.task")


class CreateTaskArgs(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Title of the task")
    description: Optional[str] = Field(None, description="Detailed description or context")
    priority: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH|URGENT)$", description="Task priority")
    status: str = Field(default="TODO", pattern="^(TODO|IN_PROGRESS|DONE|ARCHIVED)$", description="Initial status")
    due_date: Optional[datetime] = Field(None, description="Due date and time in ISO format")


class CreateTaskTool(BaseTool):
    name = "create_task"
    description = "Create a new task in the user's task management system."
    security_level = ToolSecurityLevel.SAFE
    args_schema = CreateTaskArgs

    async def execute(self, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
        task_data = TaskCreate(
            title=kwargs["title"],
            description=kwargs.get("description"),
            priority=kwargs.get("priority", "MEDIUM"),
            status=kwargs.get("status", "TODO"),
            due_date=kwargs.get("due_date"),
        )
        task = await TaskService.create_task(session=session, user_id=user_id, data=task_data)
        return ToolResult(
            success=True,
            message=f"Task '{task.title}' created successfully.",
            data={
                "task_id": task.id,
                "title": task.title,
                "priority": task.priority,
                "status": task.status,
                "due_date": task.due_date.isoformat() if task.due_date else None,
            },
        )


class ListTasksArgs(BaseModel):
    status: Optional[str] = Field(None, pattern="^(TODO|IN_PROGRESS|DONE|ARCHIVED)$", description="Filter by status")
    priority: Optional[str] = Field(None, pattern="^(LOW|MEDIUM|HIGH|URGENT)$", description="Filter by priority")
    limit: int = Field(default=50, ge=1, le=100, description="Max number of tasks to return")


class ListTasksTool(BaseTool):
    name = "list_tasks"
    description = "List existing tasks for the user, with optional filters for status and priority."
    security_level = ToolSecurityLevel.SAFE
    args_schema = ListTasksArgs

    async def execute(self, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
        tasks = await TaskService.get_tasks(
            session=session,
            user_id=user_id,
            status=kwargs.get("status"),
            priority=kwargs.get("priority"),
            limit=kwargs.get("limit", 50),
        )
        tasks_data = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "priority": t.priority,
                "status": t.status,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "created_at": t.created_at.isoformat(),
            }
            for t in tasks
        ]
        return ToolResult(
            success=True,
            message=f"Retrieved {len(tasks_data)} tasks.",
            data={"tasks": tasks_data, "count": len(tasks_data)},
        )


class UpdateTaskArgs(BaseModel):
    task_id: str = Field(..., min_length=1, description="ID of the task to update")
    title: Optional[str] = Field(None, min_length=1, max_length=255, description="New title")
    description: Optional[str] = Field(None, description="New description")
    priority: Optional[str] = Field(None, pattern="^(LOW|MEDIUM|HIGH|URGENT)$", description="New priority")
    status: Optional[str] = Field(None, pattern="^(TODO|IN_PROGRESS|DONE|ARCHIVED)$", description="New status")
    due_date: Optional[datetime] = Field(None, description="New due date in ISO format")


class UpdateTaskTool(BaseTool):
    name = "update_task"
    description = "Update an existing task's title, status, priority, description, or due date."
    security_level = ToolSecurityLevel.SAFE
    args_schema = UpdateTaskArgs

    async def execute(self, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
        task_id = kwargs["task_id"]
        update_fields = {k: v for k, v in kwargs.items() if k != "task_id" and v is not None}
        update_data = TaskUpdate(**update_fields)

        task = await TaskService.update_task(session=session, user_id=user_id, task_id=task_id, data=update_data)
        if not task:
            return ToolResult(
                success=False,
                error="TASK_NOT_FOUND",
                message=f"Task with ID '{task_id}' was not found or does not belong to you.",
            )
        return ToolResult(
            success=True,
            message=f"Task '{task.title}' updated successfully.",
            data={
                "task_id": task.id,
                "title": task.title,
                "priority": task.priority,
                "status": task.status,
                "due_date": task.due_date.isoformat() if task.due_date else None,
            },
        )


class DeleteTaskArgs(BaseModel):
    task_id: str = Field(..., min_length=1, description="ID of the task proposed for deletion")
    reason: Optional[str] = Field(None, description="Reason for proposing deletion")


class DeleteTaskTool(BaseTool):
    name = "delete_task"
    description = "Propose deleting a task. This is a guarded action that generates a pending approval request and requires human authorization before deletion executes."
    security_level = ToolSecurityLevel.GUARDED
    args_schema = DeleteTaskArgs

    async def execute(self, session: AsyncSession, user_id: str, **kwargs) -> ToolResult:
        task_id = kwargs["task_id"]
        # Verify ownership and existence
        task = await TaskService.get_task_by_id(session=session, user_id=user_id, task_id=task_id)
        if not task:
            return ToolResult(
                success=False,
                error="TASK_NOT_FOUND",
                message=f"Task with ID '{task_id}' was not found or does not belong to you.",
            )

        # Build proposed action payload
        proposed_payload = {
            "action": "delete_task",
            "task_id": task.id,
            "title": task.title,
            "reason": kwargs.get("reason"),
        }
        payload_hash = compute_canonical_payload_hash(proposed_payload)

        # Create PENDING ApprovalRequest (DO NOT delete the task)
        approval = ApprovalRequest(
            user_id=user_id,
            action_type="DELETE_TASK",
            summary=f"Delete task: '{task.title}'",
            proposed_payload=proposed_payload,
            payload_hash=payload_hash,
            status=ApprovalStatus.PENDING.value,
        )
        session.add(approval)
        await session.commit()
        await session.refresh(approval)

        logger.info(f"Guarded action: Created approval request {approval.id} for task deletion (task_id: {task.id})")

        return ToolResult(
            success=True,
            message=f"Action requires your authorization: Propose deleting task '{task.title}'. Approval Request #{approval.id} created.",
            requires_approval=True,
            approval_id=approval.id,
            data={
                "approval_id": approval.id,
                "action_type": "DELETE_TASK",
                "task_id": task.id,
                "task_title": task.title,
                "status": "PENDING",
            },
        )
