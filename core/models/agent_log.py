import enum
import uuid
from typing import Optional

from sqlalchemy import String, Text, JSON, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import mapped_column, Mapped

from core.database import Base
from core.models.base import TimestampMixin


class AgentType(str, enum.Enum):
    QUERY = "query"
    TASK_MANAGER = "task_manager"
    CODING = "coding"
    TESTING = "testing"


class AgentLogStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    IN_PROGRESS = "in_progress"


class AgentLog(Base, TimestampMixin):
    __tablename__ = "agent_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_type: Mapped[AgentType] = mapped_column(
        SAEnum(AgentType, name="agenttype"), nullable=False
    )
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tasks.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[AgentLogStatus] = mapped_column(
        SAEnum(AgentLogStatus, name="agentlogstatus"), nullable=False
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
