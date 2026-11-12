import uuid
from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.core.models.base import Base, GUID


class Ambiguity(Base):
    """Detected ambiguity, contradiction, or missing term requiring human resolution."""

    __tablename__ = "ambiguities"
    __table_args__ = {"schema": "accord"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.conversation_analyses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agreement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.agreements.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ambiguity_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        default="MEDIUM",
        nullable=False,  # HIGH, MEDIUM, LOW
    )
    clarification_question: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    suggested_options: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=list,
        nullable=False,
    )
    related_participants: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=list,
        nullable=False,
    )
    evidence_quote: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    message_indices: Mapped[List[int]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=list,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="UNRESOLVED",
        nullable=False,  # UNRESOLVED, RESOLVED
    )
    resolution_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    resolved_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    analysis = relationship("ConversationAnalysis", back_populates="ambiguities")
    conversation = relationship("Conversation")
    agreement = relationship("Agreement", back_populates="ambiguities")
    resolved_by = relationship("User", foreign_keys=[resolved_by_user_id])

    def __repr__(self) -> str:
        return f"<Ambiguity {self.id}: {self.ambiguity_type} status={self.status}>"

