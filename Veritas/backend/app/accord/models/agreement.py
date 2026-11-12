import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON
from app.core.models.base import Base, GUID, TimestampMixin


class Agreement(Base, TimestampMixin):
    """Agreement consensus entity extracted from conversation and reviewed by users."""

    __tablename__ = "agreements"
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
    analysis_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.conversation_analyses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default="DRAFT",
        nullable=False,  # DRAFT, UNDER_REVIEW, PARTIALLY_ACCEPTED, CONFIRMED, REJECTED, CHANGES_REQUESTED
    )
    total_value: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )
    terms: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=list,
        nullable=False,
    )
    is_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    confirmed_by_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    rejection_notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    submitted_for_review_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="agreements")
    analysis = relationship("ConversationAnalysis", back_populates="agreements")
    owner = relationship("User", foreign_keys=[owner_id])
    confirmed_by = relationship("User", foreign_keys=[confirmed_by_id])

    participants: Mapped[List["AgreementParticipant"]] = relationship(
        "AgreementParticipant",
        back_populates="agreement",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    versions: Mapped[List["AgreementVersion"]] = relationship(
        "AgreementVersion",
        back_populates="agreement",
        cascade="all, delete-orphan",
        order_by="AgreementVersion.version",
    )
    responses: Mapped[List["AgreementParticipantConsent"]] = relationship(
        "AgreementParticipantConsent",
        back_populates="agreement",
        cascade="all, delete-orphan",
        order_by="desc(AgreementParticipantConsent.created_at)",
    )
    obligations: Mapped[List["Obligation"]] = relationship(
        "Obligation",
        back_populates="agreement",
        cascade="all, delete-orphan",
    )
    expense_splits: Mapped[List["ExpenseSplit"]] = relationship(
        "ExpenseSplit",
        back_populates="agreement",
        cascade="all, delete-orphan",
    )
    ambiguities: Mapped[List["Ambiguity"]] = relationship(
        "Ambiguity",
        back_populates="agreement",
    )
    history: Mapped[List["AgreementHistory"]] = relationship(
        "AgreementHistory",
        back_populates="agreement",
        cascade="all, delete-orphan",
        order_by="desc(AgreementHistory.created_at)",
    )
    payment_requests: Mapped[List["PaymentRequest"]] = relationship(
        "PaymentRequest",
        back_populates="agreement",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Agreement {self.id}: {self.title} v{self.version} status={self.status}>"


class AgreementParticipant(Base):
    """Participant role and individual consent status associated with an agreement."""

    __tablename__ = "agreement_participants"
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
    participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.participants.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    stated_role: Mapped[str] = mapped_column(
        String(50),
        default="PARTICIPANT",
        nullable=False,
    )
    consent_status: Mapped[str] = mapped_column(
        String(32),
        default="PENDING",
        nullable=False,  # PENDING, ACCEPTED, REJECTED, REQUESTED_CHANGES
    )
    responded_version: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    responded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_confirmed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    bound_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    bound_method: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,  # DIRECT_ASSIGNMENT, INVITATION
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    agreement = relationship("Agreement", back_populates="participants")
    user = relationship("User", foreign_keys=[user_id], lazy="selectin")
    responses: Mapped[List["AgreementParticipantConsent"]] = relationship(
        "AgreementParticipantConsent",
        back_populates="agreement_participant",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    invitations: Mapped[List["ParticipantInvitation"]] = relationship(
        "ParticipantInvitation",
        back_populates="participant",
        cascade="all, delete-orphan",
        order_by="desc(ParticipantInvitation.created_at)",
        lazy="selectin",
    )

    @property
    def bound_user_email(self) -> Optional[str]:
        return self.user.email if self.user else None

    @property
    def bound_user_name(self) -> Optional[str]:
        return self.user.full_name if self.user else None


class AgreementVersion(Base):
    """Snapshot of agreement terms, summary, and value for each revision version."""

    __tablename__ = "agreement_versions"
    __table_args__ = (
        UniqueConstraint("agreement_id", "version", name="uq_accord_agreement_version"),
        {"schema": "accord"},
    )

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
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    terms: Mapped[List[str]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=list,
        nullable=False,
    )
    total_value: Mapped[Decimal] = mapped_column(
        Numeric(14, 4),
        default=Decimal("0.0000"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        default="USD",
        nullable=False,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    agreement = relationship("Agreement", back_populates="versions")
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class AgreementParticipantConsent(Base):
    """Individual participant consent response per agreement version."""

    __tablename__ = "agreement_participant_responses"
    __table_args__ = (
        UniqueConstraint("agreement_participant_id", "version", name="uq_participant_response_version"),
        {"schema": "accord"},
    )

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
    agreement_participant_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.agreement_participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("accord.participants.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    response: Mapped[str] = mapped_column(
        String(32),
        nullable=False,  # ACCEPTED, REJECTED, REQUESTED_CHANGES
    )
    comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    agreement = relationship("Agreement", back_populates="responses")
    agreement_participant = relationship("AgreementParticipant", back_populates="responses")
    user = relationship("User", foreign_keys=[user_id])


class AgreementHistory(Base):
    """Audit log of decisions, revisions, confirmations, and rejections on an agreement."""

    __tablename__ = "agreement_history"
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
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,  # CREATED, EDITED, SUBMITTED_FOR_REVIEW, PARTICIPANT_ACCEPTED, PARTICIPANT_REJECTED, PARTICIPANT_REQUESTED_CHANGES, CONFIRMED, REJECTED
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    changes: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        default=dict,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    agreement = relationship("Agreement", back_populates="history")
    user = relationship("User", foreign_keys=[user_id])


class ParticipantInvitation(Base):
    """Cryptographically secure, single-use invitation token for binding a user account to a participant."""

    __tablename__ = "participant_invitations"
    __table_args__ = (
        Index("ix_accord_part_inv_token_hash", "token_hash", unique=True),
        {"schema": "accord"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    agreement_participant_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.agreement_participants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agreement_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("accord.agreements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Stored as SHA-256 hash (64 hex characters) - plaintext token is never stored in DB
    token_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    is_claimed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    claimed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    claimed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID,
        ForeignKey("core.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    participant = relationship("AgreementParticipant", back_populates="invitations")
    agreement = relationship("Agreement")
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    claimed_by = relationship("User", foreign_keys=[claimed_by_user_id])

    @property
    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_claimed and not self.is_expired

