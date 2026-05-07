import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Float, Integer, DateTime, JSON, Enum as SAEnum
from sqlalchemy.orm import mapped_column, Mapped

from core.database import Base
from core.models.base import TimestampMixin


class TaskStatus(str, enum.Enum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    IN_DEVELOPMENT = "in_development"
    TESTING = "testing"
    IN_REVIEW = "in_review"
    PENDING_DEPLOYMENT = "pending_deployment"
    DEPLOYED = "deployed"
    REJECTED = "rejected"
    ESCALATED = "escalated"


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, name="taskstatus", values_callable=lambda x: [e.value for e in x]),
        default=TaskStatus.PENDING_APPROVAL,
        nullable=False,
    )
    priority_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vote_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requested_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    required_capabilities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deployed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    escalation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
