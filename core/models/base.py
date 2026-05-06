"""
Shared mixin for created_at / updated_at timestamps.
Uses declared_attr so SQLAlchemy 2.0 correctly applies columns in subclasses.
"""
from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlalchemy.orm import declared_attr, mapped_column, Mapped


class TimestampMixin:
    @declared_attr
    def created_at(cls) -> Mapped[datetime]:
        return mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(timezone.utc),
            nullable=False,
        )

    @declared_attr
    def updated_at(cls) -> Mapped[datetime]:
        return mapped_column(
            DateTime(timezone=True),
            default=lambda: datetime.now(timezone.utc),
            onupdate=lambda: datetime.now(timezone.utc),
            nullable=False,
        )
