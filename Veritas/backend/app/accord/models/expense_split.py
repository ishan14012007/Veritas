import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.models.base import Base, GUID


class ExpenseSplit(Base):
    """Expense-sharing arrangement proposed or confirmed within an agreement."""

    __tablename__ = "expense_splits"
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
        String(200),
        nullable=False,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )
    split_method: Mapped[str] = mapped_column(
        String(20),
        default="EQUAL",
        nullable=False,  # EQUAL, PERCENTAGE, CUSTOM, UNEQUAL
    )
    proposer_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="PROPOSED",
        nullable=False,  # PROPOSED, CONFIRMED, SETTLED
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    agreement = relationship("Agreement", back_populates="expense_splits")
    analysis = relationship("ConversationAnalysis", back_populates="expense_splits")
    shares: Mapped[List["SplitShare"]] = relationship(
        "SplitShare",
        back_populates="expense_split",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ExpenseSplit {self.id}: {self.title} total={self.total_amount}>"


class SplitShare(Base):
    """Individual participant share within an expense split."""

    __tablename__ = "split_shares"
    __table_args__ = {"schema": "accord"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    expense_split_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.expense_splits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    participant_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    share_value: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        default=Decimal("1.0000"),
        nullable=False,
    )
    computed_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        nullable=False,
    )
    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    net_balance: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="UNPAID",
        nullable=False,  # UNPAID, PAID
    )
    payment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    expense_split = relationship("ExpenseSplit", back_populates="shares")
