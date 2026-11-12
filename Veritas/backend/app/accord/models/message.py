import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.models.base import Base, GUID


class Message(Base):
    """Normalized chronologically ordered message extracted from conversation transcript.
    Resides in the 'accord' PostgreSQL schema.
    """

    __tablename__ = "messages"
    __table_args__ = {"schema": "accord"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.participants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sender_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    message_body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    original_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    order_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    is_system_message: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    participant = relationship("Participant", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message {self.id} idx={self.order_index} sender='{self.sender_name}'>"

