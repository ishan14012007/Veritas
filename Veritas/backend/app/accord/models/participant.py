import uuid
from datetime import datetime, timezone
from typing import List
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.models.base import Base, GUID


class Participant(Base):
    """Identified unique conversation participant.
    Resides in the 'accord' PostgreSQL schema.
    """

    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sender_identifier", name="uq_accord_conversation_participant"),
        {"schema": "accord"},
    )

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
    display_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    sender_identifier: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="participants")
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="participant",
    )

    def __repr__(self) -> str:
        return f"<Participant {self.id}: {self.display_name} in {self.conversation_id}>"

