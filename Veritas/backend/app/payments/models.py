import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.core.models.base import Base, GUID
import app.accord.models  # ensure Agreement and Obligation mappers are registered


class PaymentRequest(Base):
    """Payment request associated with a confirmed agreement and obligation."""

    __tablename__ = "payment_requests"
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
    agreement_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    obligation_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.obligations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    debtor_participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.agreement_participants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    creditor_participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.agreement_participants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    debtor_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    creditor_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    receiver_merchant_account: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
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
    status: Mapped[str] = mapped_column(
        String(32),
        default="DRAFT",
        nullable=False,
        index=True,
        # DRAFT, PENDING, APPROVED, PROCESSING, COMPLETED, FAILED, CANCELLED, REFUNDED, PARTIALLY_REFUNDED
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    paypal_order_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    agreement = relationship("Agreement", back_populates="payment_requests")
    obligation = relationship("Obligation", back_populates="payment_requests")
    debtor_participant = relationship("AgreementParticipant", foreign_keys=[debtor_participant_id])
    creditor_participant = relationship("AgreementParticipant", foreign_keys=[creditor_participant_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])

    orders: Mapped[List["PayPalOrder"]] = relationship(
        "PayPalOrder",
        back_populates="payment_request",
        cascade="all, delete-orphan",
        order_by="desc(PayPalOrder.created_at)",
        lazy="selectin",
    )
    captures: Mapped[List["PaymentCapture"]] = relationship(
        "PaymentCapture",
        back_populates="payment_request",
        cascade="all, delete-orphan",
        order_by="desc(PaymentCapture.created_at)",
        lazy="selectin",
    )
    history: Mapped[List["PaymentHistory"]] = relationship(
        "PaymentHistory",
        back_populates="payment_request",
        cascade="all, delete-orphan",
        order_by="desc(PaymentHistory.created_at)",
        lazy="selectin",
    )
    refunds: Mapped[List["PaymentRefund"]] = relationship(
        "PaymentRefund",
        back_populates="payment_request",
        cascade="all, delete-orphan",
        order_by="desc(PaymentRefund.created_at)",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<PaymentRequest {self.id}: {self.amount} {self.currency} status={self.status}>"


class PayPalOrder(Base):
    """Internal record of PayPal Orders v2 resource."""

    __tablename__ = "paypal_orders"
    __table_args__ = {"schema": "accord"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    payment_request_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.payment_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paypal_order_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
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
    status: Mapped[str] = mapped_column(
        String(32),
        default="CREATED",
        nullable=False,
        # CREATED, SAVED, APPROVED, VOIDED, COMPLETED, PAYER_ACTION_REQUIRED
    )
    approval_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )
    custom_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    reference_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    payment_request = relationship("PaymentRequest", back_populates="orders")

    def __repr__(self) -> str:
        return f"<PayPalOrder {self.id}: paypal_order_id={self.paypal_order_id} status={self.status}>"


class PaymentCapture(Base):
    """Server-side captured payment details from PayPal."""

    __tablename__ = "payment_captures"
    __table_args__ = {"schema": "accord"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    payment_request_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.payment_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paypal_order_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )
    paypal_capture_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
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
    status: Mapped[str] = mapped_column(
        String(32),
        default="COMPLETED",
        nullable=False,
        # COMPLETED, PENDING, FAILED, REFUNDED, PARTIALLY_REFUNDED
    )
    paypal_fee: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4),
        default=Decimal("0.0000"),
        nullable=True,
    )
    net_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(14, 4),
        nullable=True,
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    payment_request = relationship("PaymentRequest", back_populates="captures")
    refunds: Mapped[List["PaymentRefund"]] = relationship(
        "PaymentRefund",
        back_populates="payment_capture",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<PaymentCapture {self.id}: capture_id={self.paypal_capture_id} status={self.status}>"


class PaymentWebhookEvent(Base):
    """Idempotent audit record of received PayPal webhook events."""

    __tablename__ = "payment_webhook_events"
    __table_args__ = {"schema": "accord"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    paypal_event_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    resource_type: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        index=True,
    )
    verification_status: Mapped[str] = mapped_column(
        String(32),
        default="VERIFIED",
        nullable=False,
        # VERIFIED, FAILED, SIMULATED
    )
    processing_status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        nullable=False,
        index=True,
        # PENDING, PROCESSED, FAILED, IGNORED
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=dict,
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return f"<PaymentWebhookEvent {self.id}: {self.event_type} id={self.paypal_event_id} status={self.processing_status}>"


class PaymentHistory(Base):
    """Audit ledger tracking all payment lifecycle transitions."""

    __tablename__ = "payment_history"
    __table_args__ = {"schema": "accord"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    payment_request_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.payment_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        # REQUEST_CREATED, ORDER_CREATED, PAYER_APPROVED, CAPTURE_ATTEMPTED, CAPTURE_SUCCEEDED, CAPTURE_FAILED, WEBHOOK_CONFIRMED, REFUND_ISSUED, CANCELLED
    )
    from_status: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    to_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    performed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    details: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    payment_request = relationship("PaymentRequest", back_populates="history")
    performed_by = relationship("User", foreign_keys=[performed_by_user_id])

    def __repr__(self) -> str:
        return f"<PaymentHistory {self.id}: {self.action} {self.from_status}->{self.to_status}>"


class PaymentRefund(Base):
    """Refund record associated with a captured payment."""

    __tablename__ = "payment_refunds"
    __table_args__ = {"schema": "accord"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    payment_capture_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.payment_captures.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_request_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.payment_requests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    paypal_refund_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
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
    status: Mapped[str] = mapped_column(
        String(32),
        default="COMPLETED",
        nullable=False,
        # COMPLETED, PENDING, FAILED
    )
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    refunded_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    payment_capture = relationship("PaymentCapture", back_populates="refunds")
    payment_request = relationship("PaymentRequest", back_populates="refunds")
    refunded_by = relationship("User", foreign_keys=[refunded_by_user_id])

    def __repr__(self) -> str:
        return f"<PaymentRefund {self.id}: refund_id={self.paypal_refund_id} amount={self.amount}>"

