import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.core.models.base import Base, GUID, TimestampMixin


class ConversationAnalysis(Base, TimestampMixin):
    """Analysis record capturing an extraction run on a conversation transcript."""

    __tablename__ = "conversation_analyses"
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
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="QUEUED",
        nullable=False,  # QUEUED, PROCESSING, COMPLETED, FAILED
    )
    ai_model: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    overall_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    raw_ai_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    token_count: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    execution_duration_ms: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="analyses")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    agreements: Mapped[List["Agreement"]] = relationship(
        "Agreement",
        back_populates="analysis",
    )
    financial_facts: Mapped[List["FinancialFact"]] = relationship(
        "FinancialFact",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    obligations: Mapped[List["Obligation"]] = relationship(
        "Obligation",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    expense_splits: Mapped[List["ExpenseSplit"]] = relationship(
        "ExpenseSplit",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )
    ambiguities: Mapped[List["Ambiguity"]] = relationship(
        "Ambiguity",
        back_populates="analysis",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ConversationAnalysis {self.id} status={self.status} model={self.ai_model}>"

