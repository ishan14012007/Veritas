import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class CreatePaymentRequestRequest(BaseModel):
    """Payload to initiate a payment request against an eligible confirmed obligation."""
    obligation_id: uuid.UUID
    amount: Optional[Decimal] = Field(default=None, gt=Decimal("0.00"))
    notes: Optional[str] = Field(default=None, max_length=500)


class CancelPaymentRequest(BaseModel):
    """Payload to cancel an unpaid payment request."""
    reason: Optional[str] = Field(default=None, max_length=500)


class CreatePayPalOrderRequest(BaseModel):
    """Payload to create a PayPal Order for an active payment request."""
    payment_request_id: uuid.UUID


class CapturePayPalOrderRequest(BaseModel):
    """Payload sent by frontend onApprove to trigger server-side capture."""
    order_id: str = Field(min_length=1, max_length=128)


class RefundPaymentRequest(BaseModel):
    """Payload to initiate a full or partial refund of a captured payment."""
    reason: Optional[str] = Field(default=None, max_length=500)
    amount: Optional[Decimal] = Field(default=None, gt=Decimal("0.00"))


class PayPalOrderResponse(BaseModel):
    """Details of a created or retrieved PayPal Order."""
    id: uuid.UUID
    payment_request_id: uuid.UUID
    paypal_order_id: str
    amount: Decimal
    currency: str
    status: str
    approval_url: Optional[str] = None
    client_id: str
    is_mock: bool = False
    original_amount: Optional[Decimal] = None
    original_currency: Optional[str] = None
    exchange_rate: Optional[Decimal] = None
    is_converted: bool = False

    model_config = ConfigDict(from_attributes=True)


class PaymentCaptureResponse(BaseModel):
    """Details of a server-side captured PayPal payment."""
    id: uuid.UUID
    payment_request_id: uuid.UUID
    paypal_order_id: str
    paypal_capture_id: str
    amount: Decimal
    currency: str
    status: str
    paypal_fee: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    captured_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentRefundResponse(BaseModel):
    """Details of a processed refund."""
    id: uuid.UUID
    payment_capture_id: uuid.UUID
    payment_request_id: uuid.UUID
    paypal_refund_id: str
    amount: Decimal
    currency: str
    status: str
    reason: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentHistoryResponse(BaseModel):
    """Audit entry for payment lifecycle transitions."""
    id: uuid.UUID
    payment_request_id: uuid.UUID
    action: str
    from_status: Optional[str] = None
    to_status: str
    performed_by_user_id: Optional[uuid.UUID] = None
    details: Dict[str, Any] = {}
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentRequestResponse(BaseModel):
    """Full representation of a payment request linked to an obligation."""
    id: uuid.UUID
    agreement_id: uuid.UUID
    agreement_version: int
    obligation_id: uuid.UUID
    debtor_participant_id: Optional[uuid.UUID] = None
    creditor_participant_id: Optional[uuid.UUID] = None
    debtor_name: str
    creditor_name: str
    receiver_merchant_account: str
    amount: Decimal
    currency: str
    status: str
    due_date: Optional[datetime] = None
    paypal_order_id: Optional[str] = None
    created_by_user_id: Optional[uuid.UUID] = None
    created_at: datetime
    updated_at: datetime
    can_pay: bool = False
    can_cancel: bool = False
    can_refund: bool = False
    is_mock: bool = False
    active_order: Optional[PayPalOrderResponse] = None
    latest_capture: Optional[PaymentCaptureResponse] = None
    argus_verification: Optional[Dict[str, Any]] = None
    paypal_amount: Optional[Decimal] = None
    paypal_currency: Optional[str] = None
    exchange_rate: Optional[Decimal] = None
    is_converted: bool = False

    model_config = ConfigDict(from_attributes=True)


class ObligationPaymentSummary(BaseModel):
    """Consolidated status of an individual obligation and its payment request."""
    obligation_id: uuid.UUID
    title: str
    description: str
    debtor_name: Optional[str] = None
    creditor_name: Optional[str] = None
    amount: Decimal
    currency: str
    obligation_status: str
    is_settled: bool
    settled_amount: Decimal = Decimal("0.00")
    outstanding_amount: Decimal = Decimal("0.00")
    is_eligible_for_payment: bool
    ineligibility_reason: Optional[str] = None
    payment_request: Optional[PaymentRequestResponse] = None

    model_config = ConfigDict(from_attributes=True)


class AgreementSettlementSummaryResponse(BaseModel):
    """Overall settlement and collection overview for an agreement."""
    agreement_id: uuid.UUID
    agreement_title: str
    agreement_version: int
    agreement_status: str
    consensus_achieved: bool
    total_obligations_amount: Decimal
    currency: str
    total_completed_amount: Decimal
    total_pending_amount: Decimal
    total_failed_amount: Decimal
    outstanding_balance: Decimal
    settlement_status: str  # UNSETTLED, PARTIALLY_SETTLED, FULLY_SETTLED
    obligations: List[ObligationPaymentSummary]
    payment_requests: List[PaymentRequestResponse]

    model_config = ConfigDict(from_attributes=True)


class WebhookProcessingResult(BaseModel):
    """Result of processing a PayPal webhook event."""
    event_id: str
    event_type: str
    verification_status: str
    processing_status: str
    message: str

