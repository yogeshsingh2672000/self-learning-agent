"""
ChatHistory model for storing conversation messages between users and agents.
"""
import enum
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import mapped_column, Mapped, relationship

from core.database import Base
from core.models.base import TimestampMixin


class MessageRole(str, enum.Enum):
    """Role of the message sender"""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class ChatHistory(Base, TimestampMixin):
    """
    Stores conversation history between users and the Query Agent.
    Each message is stored separately for easy retrieval and analysis.
    """
    __tablename__ = "chat_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    
    # Reference to the user who initiated the conversation
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )
    
    # Conversation session ID (can group multiple messages)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # Role: user or agent
    role: Mapped[MessageRole] = mapped_column(
        SAEnum(MessageRole, name="messagerole", values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )
    
    # The actual message content
    message: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Optional: ID of the task created from this message (if it triggered a capability gap)
    task_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"),
        nullable=True
    )
    
    # Metadata: Was this message a capability gap detection?
    is_capability_gap: Mapped[bool] = mapped_column(default=False, nullable=False)
    
    # Metadata: What was the gap (if detected)?
    gap_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata: Suggested tool/capability to close the gap
    suggested_tool: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # Message timestamp (when exactly was this sent)
    message_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    def __repr__(self):
        return f"<ChatHistory {self.id} - {self.role}: {self.message[:50]}...>"
