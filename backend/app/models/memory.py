from typing import Optional, Dict, Any
from sqlalchemy import String, Text, Boolean, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, generate_uuid


class UserMemory(Base, TimestampMixin):
    """Structured user knowledge item (preference, work style, fact, contact)."""
    __tablename__ = "user_memories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(50), default="PREFERENCE", index=True, nullable=False)
    key: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="memories")
