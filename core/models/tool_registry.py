import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime
from sqlalchemy.orm import mapped_column, Mapped

from core.database import Base
from core.models.base import TimestampMixin


class ToolRegistryEntry(Base, TimestampMixin):
    __tablename__ = "tool_registry_db"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tool_name: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    deployed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    previous_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
