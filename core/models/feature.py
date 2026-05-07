import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, JSON, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import mapped_column, Mapped

from core.database import Base
from core.models.base import TimestampMixin


class FeatureStatus(str, enum.Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    IN_REVIEW = "in_review"
    DEPLOYED = "deployed"
    FAILED = "failed"


class Feature(Base, TimestampMixin):
    __tablename__ = "features"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tasks.id"), nullable=False, index=True
    )
    branch_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tool_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tool_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    test_code: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    test_results: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    pr_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    pr_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pr_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[FeatureStatus] = mapped_column(
        SAEnum(FeatureStatus, name="featurestatus", values_callable=lambda x: [e.value for e in x]),
        default=FeatureStatus.DEVELOPMENT,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    merged_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
