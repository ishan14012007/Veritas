import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.core.models.base import Base, GUID


class FinancialFact(Base):
    """Extracted financial fact linked directly to transcript message evidence."""

    __tablename__ = "financial_facts"
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
    amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )
    classification: Mapped[str] = mapped_column(
        String(32),
        nullable=False,  # PAID, PROMISED, REQUESTED, PROPOSED, MENTIONED, UNCLEAR
    )
    payer_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    recipient_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    description: Mapped[str] = mapped_column(
        Text,
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
    confidence: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
    )
    is_explicit: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    analysis = relationship("ConversationAnalysis", back_populates="financial_facts")
    conversation = relationship("Conversation")
    agreement = relationship("Agreement")

    def __repr__(self) -> str:
        return f"<FinancialFact {self.id}: {self.classification} {self.amount} {self.currency}>"

