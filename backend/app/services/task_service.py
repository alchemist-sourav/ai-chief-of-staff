import logging
from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.task import Task
from app.schemas.task import TaskCreate, TaskUpdate

logger = logging.getLogger("ai_chief_of_staff.tasks")


class TaskService:
    """Service managing user tasks and scheduling."""

    @staticmethod
    async def create_task(
        session: AsyncSession,
        user_id: str,
        data: TaskCreate,
    ) -> Task:
        """Create a new task."""
        task = Task(
            user_id=user_id,
            title=data.title,
            description=data.description,
            priority=data.priority,
            status=data.status,
            due_date=data.due_date,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        logger.info(f"Task '{task.title}' ({task.id}) created for user {user_id}")
        return task

    @staticmethod
    async def get_tasks(
        session: AsyncSession,
        user_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100,
    ) -> List[Task]:
        """Fetch tasks for a user with optional filters."""
        filters = [Task.user_id == user_id]
        if status:
            filters.append(Task.status == status.upper())
        if priority:
            filters.append(Task.priority == priority.upper())

        query = (
            select(Task)
            .where(and_(*filters))
            .order_by(Task.due_date.asc().nulls_last(), Task.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_task_by_id(
        session: AsyncSession,
        user_id: str,
        task_id: str,
    ) -> Optional[Task]:
        """Fetch single task by ID ensuring tenant isolation."""
        query = select(Task).where(and_(Task.id == task_id, Task.user_id == user_id))
        result = await session.execute(query)
        return result.scalars().first()

    @staticmethod
    async def update_task(
        session: AsyncSession,
        user_id: str,
        task_id: str,
        data: TaskUpdate,
    ) -> Optional[Task]:
        """Update existing task fields."""
        task = await TaskService.get_task_by_id(session, user_id, task_id)
        if not task:
            return None

        update_dict = data.model_dump(exclude_unset=True, exclude_none=True)
        for key, value in update_dict.items():
            setattr(task, key, value)

        await session.commit()
        await session.refresh(task)
        logger.info(f"Task {task_id} updated for user {user_id}")
        return task

    @staticmethod
    async def delete_task(
        session: AsyncSession,
        user_id: str,
        task_id: str,
    ) -> bool:
        """Delete task ensuring tenant isolation."""
        task = await TaskService.get_task_by_id(session, user_id, task_id)
        if not task:
            return False

        await session.delete(task)
        await session.commit()
        logger.info(f"Task {task_id} deleted for user {user_id}")
        return True
