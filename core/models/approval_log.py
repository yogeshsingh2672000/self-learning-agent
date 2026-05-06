import enum
import uuid
from typing import Optional

from sqlalchemy import String, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import mapped_column, Mapped

from core.database import Base
from core.models.base import TimestampMixin


class ApprovalDecision(str, enum.Enum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalLog(Base, TimestampMixin):
    __tablename__ = "approval_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id"), nullable=False, index=True
    )
    approver: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[ApprovalDecision] = mapped_column(
        SAEnum(ApprovalDecision, name="approvaldecision"), nullable=False
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
