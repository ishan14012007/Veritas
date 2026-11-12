import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.core.models.base import Base, GUID


class Obligation(Base):
    """Obligation, responsibility, deliverable, or milestone extracted from agreement."""

    __tablename__ = "obligations"
    __table_args__ = {"schema": "accord"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    agreement_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.agreements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    analysis_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.conversation_analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    debtor_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    creditor_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4),
        nullable=True,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )
    due_date_raw: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        nullable=False,  # PENDING, FULFILLED, WAIVED
    )
    is_freelance_milestone: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    deliverable: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    condition: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    agreement = relationship("Agreement", back_populates="obligations")
    analysis = relationship("ConversationAnalysis", back_populates="obligations")
    payment_requests = relationship("PaymentRequest", back_populates="obligation")

    def __repr__(self) -> str:
        return f"<Obligation {self.id}: {self.title} status={self.status}>"

