import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.core.models.base import Base, GUID, TimestampMixin

json_type = JSON().with_variant(JSONB(), "postgresql")


class WhatsAppAccount(Base, TimestampMixin):
    """WhatsApp account linked to an authenticated VERITAS user."""

    __tablename__ = "whatsapp_accounts"
    __table_args__ = (
        Index("ix_whatsapp_accounts_user_id", "user_id"),
        Index("ix_whatsapp_accounts_phone_number", "phone_number"),
        {"schema": "accord"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    phone_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        unique=True,
    )
    display_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(
        String(32),
        default="mock",
        nullable=False,
    )
    phone_number_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    business_account_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    connection_status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING_VERIFICATION",
        nullable=False,  # PENDING_VERIFICATION, CONNECTED, DISCONNECTED
    )
    consent_status: Mapped[str] = mapped_column(
        String(32),
        default="OPTED_OUT",
        nullable=False,  # OPTED_IN, OPTED_OUT
    )
    verification_token: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    verification_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    messages: Mapped[List["WhatsAppMessage"]] = relationship(
        "WhatsAppMessage",
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="desc(WhatsAppMessage.created_at)",
    )


class WhatsAppMessage(Base, TimestampMixin):
    """WhatsApp message tracking inbound and outbound messages with delivery states."""

    __tablename__ = "whatsapp_messages"
    __table_args__ = (
        Index("ix_whatsapp_messages_provider_id", "provider_message_id"),
        Index("ix_whatsapp_messages_conversation_id", "conversation_id"),
        Index("ix_whatsapp_messages_sender", "sender_number"),
        Index("ix_whatsapp_messages_recipient", "recipient_number"),
        {"schema": "accord"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.whatsapp_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.conversations.id", ondelete="SET NULL"),
        nullable=True,
    )
    accord_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    provider_message_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
    )
    sender_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    recipient_number: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )
    direction: Mapped[str] = mapped_column(
        String(16),
        nullable=False,  # INBOUND, OUTBOUND
    )
    message_type: Mapped[str] = mapped_column(
        String(32),
        default="TEXT",
        nullable=False,  # TEXT, TEMPLATE, INTERACTIVE, MEDIA
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    raw_payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=True,
    )
    provider: Mapped[str] = mapped_column(
        String(32),
        default="mock",
        nullable=False,
    )
    delivery_status: Mapped[str] = mapped_column(
        String(32),
        default="SENT",
        nullable=False,  # QUEUED, SENT, DELIVERED, READ, FAILED
    )
    error_code: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_mock: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    account = relationship("WhatsAppAccount", back_populates="messages")
    conversation = relationship("Conversation", foreign_keys=[conversation_id])


class WhatsAppWebhookEvent(Base):
    """Raw received WhatsApp webhook events for audit, signature verification, and deduplication."""

    __tablename__ = "whatsapp_webhook_events"
    __table_args__ = (
        Index("ix_whatsapp_webhook_events_idempotency_key", "idempotency_key", unique=True),
        Index("ix_whatsapp_webhook_events_provider_event_id", "provider_event_id"),
        {"schema": "accord"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    provider_event_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,  # MESSAGES, MESSAGE_STATUS, TEMPLATE_STATUS
    )
    signature_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    processing_status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        nullable=False,  # PENDING, PROCESSED, FAILED, DUPLICATE
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(
        json_type,
        nullable=False,
    )
    error_detail: Mapped[Optional[str]] = mapped_column(
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


class WhatsAppMessageTemplate(Base, TimestampMixin):
    """WhatsApp pre-approved message templates for business-initiated notifications."""

    __tablename__ = "whatsapp_message_templates"
    __table_args__ = (
        Index("ix_whatsapp_message_templates_name", "template_name", unique=True),
        {"schema": "accord"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    template_name: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
    )
    language: Mapped[str] = mapped_column(
        String(16),
        default="en_US",
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(64),
        default="UTILITY",
        nullable=False,  # UTILITY, MARKETING, AUTHENTICATION
    )
    approval_status: Mapped[str] = mapped_column(
        String(32),
        default="APPROVED",
        nullable=False,  # APPROVED, PENDING, REJECTED
    )
    provider_template_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    content_structure: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        json_type,
        nullable=True,
    )
