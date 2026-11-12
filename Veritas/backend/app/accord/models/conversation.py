import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.models.base import Base, GUID, TimestampMixin


class Conversation(Base, TimestampMixin):
    """Conversation entity storing raw ingested text or WhatsApp export transcripts.
    Resides in the 'accord' PostgreSQL schema.
    """

    __tablename__ = "conversations"
    __table_args__ = {"schema": "accord"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,  # PASTED_TEXT or WHATSAPP_EXPORT
    )
    original_filename: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    raw_transcript: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    processing_status: Mapped[str] = mapped_column(
        String(20),
        default="COMPLETED",
        nullable=False,  # PENDING, PROCESSING, COMPLETED, FAILED
    )
    retention_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    owner = relationship("User", foreign_keys=[owner_id])
    participants: Mapped[List["Participant"]] = relationship(
        "Participant",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Participant.display_name",
    )
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.order_index",
    )
    analyses: Mapped[List["ConversationAnalysis"]] = relationship(
        "ConversationAnalysis",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    agreements: Mapped[List["Agreement"]] = relationship(
        "Agreement",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Conversation {self.id}: {self.title} ({self.source_type})>"

