import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.models.base import Base, GUID, TimestampMixin


class User(Base, TimestampMixin):
    """User account entity stored in schema core."""

    __tablename__ = "users"
    __table_args__ = {"schema": "core"}

    id: Mapped[uuid.UUID] = mapped_column(
        GUID,
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    phone_number: Mapped[Optional[str]] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    full_name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(32),
        default="USER",
        nullable=False,
    )
    whatsapp_opt_in: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    whatsapp_opt_in_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Relationships
    owned_organizations = relationship("Organization", back_populates="owner")
    organization_memberships = relationship("OrganizationMember", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"

