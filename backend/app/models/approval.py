import json
import hashlib
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Text, DateTime, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin, generate_uuid


class ApprovalStatus(str, Enum):
    """Lifecycle states for human-in-the-loop approval requests."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


def compute_canonical_payload_hash(payload: Dict[str, Any]) -> str:
    """Compute a deterministic SHA-256 hash using canonical JSON serialization.
    
    Guarantees that key ordering or minor whitespace variations in dictionaries
    produce an identical, verifiable cryptographic signature.
    """
    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class ApprovalRequest(Base, TimestampMixin):
    """Database model storing action proposals requiring explicit human authorization."""
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    proposed_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=ApprovalStatus.PENDING.value, index=True, nullable=False
    )
    user_comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    execution_result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationship to user
    user: Mapped["User"] = relationship("User", back_populates="approval_requests")
