from typing import Optional, Dict, Any
from sqlalchemy import String, Text, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, generate_uuid


class Message(Base, TimestampMixin):
    """Message entity representing user prompts, assistant replies, and system instructions."""
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sender_role: Mapped[str] = mapped_column(String(50), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tool_calls: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict, nullable=True)

    # Relationship
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
