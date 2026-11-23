from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.services.task_service import TaskService
from app.schemas.task import TaskCreate, TaskUpdate, TaskRead

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("", response_model=List[TaskRead])
async def list_tasks(
    status_filter: Optional[str] = Query(None, alias="status"),
    priority_filter: Optional[str] = Query(None, alias="priority"),
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List user tasks with optional filters."""
    return await TaskService.get_tasks(
        session=session,
        user_id=current_user.id,
        status=status_filter,
        priority=priority_filter,
        limit=limit,
    )


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Create a new task."""
    return await TaskService.create_task(
        session=session,
        user_id=current_user.id,
        data=data,
    )


@router.get("/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Fetch task by ID."""
    task = await TaskService.get_task_by_id(session=session, user_id=current_user.id, task_id=task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: str,
    data: TaskUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Update task details or toggle status."""
    task = await TaskService.update_task(
        session=session,
        user_id=current_user.id,
        task_id=task_id,
        data=data,
    )
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return task


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Delete task."""
    deleted = await TaskService.delete_task(
        session=session,
        user_id=current_user.id,
        task_id=task_id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return None
