from typing import List, Optional, Any
from sqlalchemy import String, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, generate_uuid


class User(Base, TimestampMixin):
    """User account entity."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    preferences: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)

    # Relationships
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation", back_populates="user", cascade="all, delete-orphan"
    )
    tasks: Mapped[List["Task"]] = relationship(
        "Task", back_populates="user", cascade="all, delete-orphan"
    )
    memories: Mapped[List["UserMemory"]] = relationship(
        "UserMemory", back_populates="user", cascade="all, delete-orphan"
    )
    approval_requests: Mapped[List["ApprovalRequest"]] = relationship(
        "ApprovalRequest", back_populates="user", cascade="all, delete-orphan"
    )
