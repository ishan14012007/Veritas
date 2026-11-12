import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class LinkPhoneNumberRequest(BaseModel):
    """Request to initiate phone number linking to an authenticated user account."""
    phone_number: str = Field(..., description="E.164 phone number, e.g. +14155552671")
    display_name: Optional[str] = Field(None, max_length=150)


class VerifyPhoneNumberRequest(BaseModel):
    """Request to complete phone number verification with single-use token."""
    phone_number: str = Field(..., description="E.164 phone number, e.g. +14155552671")
    verification_token: str = Field(..., min_length=4, max_length=64)


class WhatsAppAccountResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    phone_number: str
    display_name: Optional[str] = None
    provider: str
    phone_number_id: Optional[str] = None
    connection_status: str
    consent_status: str
    verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    verification_token: Optional[str] = None  # Populated in mock mode to facilitate testing

    model_config = ConfigDict(from_attributes=True)


class SendWhatsAppMessageRequest(BaseModel):
    """Request to dispatch an outbound WhatsApp message."""
    recipient_number: str = Field(..., description="E.164 recipient phone number")
    message_type: str = Field("TEXT", description="TEXT, TEMPLATE, or INTERACTIVE")
    content: Optional[str] = Field(None, description="Message text body for freeform messages")
    template_name: Optional[str] = Field(None, description="Pre-approved WhatsApp template name")
    template_parameters: Optional[List[Dict[str, Any]]] = Field(None, description="Template component parameters")
    conversation_id: Optional[uuid.UUID] = Field(None, description="Optional associated ACCORD conversation")


class WhatsAppMessageResponse(BaseModel):
    id: uuid.UUID
    provider_message_id: str
    account_id: Optional[uuid.UUID] = None
    conversation_id: Optional[uuid.UUID] = None
    sender_number: str
    recipient_number: str
    direction: str
    message_type: str
    content: str
    provider: str
    delivery_status: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    is_mock: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WhatsAppWebhookEventResponse(BaseModel):
    id: uuid.UUID
    provider_event_id: str
    event_type: str
    signature_verified: bool
    processing_status: str
    idempotency_key: str
    received_at: datetime
    processed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class WhatsAppStatusResponse(BaseModel):
    provider: str
    mock_mode: bool
    phone_number_id: str
    webhook_url: str
    linked_accounts_count: int
    total_messages_count: int
    registered_templates: List[str]


class MockInboundMessageRequest(BaseModel):
    """Development simulator request to inject an inbound WhatsApp message."""
    from_number: str = Field(..., description="Sender phone number")
    content: str = Field(..., description="Message text content")
    to_number: Optional[str] = Field("15550001234", description="Business recipient phone number")
    trigger_analysis: bool = Field(False, description="Whether to trigger Gemini intelligence extraction")


class MockStatusUpdateRequest(BaseModel):
    """Development simulator request to advance message delivery status."""
    provider_message_id: str = Field(...)
    status: str = Field(..., description="SENT, DELIVERED, READ, or FAILED")
    error_code: Optional[str] = None
    error_message: Optional[str] = None

