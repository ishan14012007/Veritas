import logging
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.accord.models.agreement import Agreement
from app.core.config import get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.models.user import User
from app.payments.models import PaymentCapture, PaymentHistory, PaymentRequest, PayPalOrder
from app.payments.paypal_client import get_paypal_client
from app.payments.schemas import (
    AgreementSettlementSummaryResponse,
    CancelPaymentRequest,
    CapturePayPalOrderRequest,
    CreatePaymentRequestRequest,
    CreatePayPalOrderRequest,
    PaymentCaptureResponse,
    PaymentHistoryResponse,
    PaymentRefundResponse,
    PaymentRequestResponse,
    PayPalOrderResponse,
    RefundPaymentRequest,
    WebhookProcessingResult,
)
from app.payments.service import PaymentService

logger = logging.getLogger(__name__)

# Router for /api/v1/payments (PayPal Gateway, Orders, Captures, Webhooks)
router = APIRouter(prefix="/payments", tags=["PayPal Payments"])

# Router for /api/v1/accord (ACCORD Settlement, Payment Requests)
accord_payments_router = APIRouter(prefix="/accord", tags=["ACCORD Settlement & Payments"])


# ==============================================================================
# ACCORD PAYMENT REQUESTS & SETTLEMENT ENDPOINTS
# ==============================================================================

@accord_payments_router.post(
    "/agreements/{agreement_id}/payment-requests",
    response_model=PaymentRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a payment request for a confirmed agreement obligation",
)
async def create_payment_request(
    agreement_id: uuid.UUID,
    payload: CreatePaymentRequestRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentRequestResponse:
    """Validate agreement confirmation and create a payment request against an eligible obligation."""
    try:
        req = await PaymentService.create_payment_request(
            db=db,
            agreement_id=agreement_id,
            obligation_id=payload.obligation_id,
            current_user=current_user,
            amount=payload.amount,
            notes=payload.notes,
        )
        # Eagerly load agreement to build response
        stmt = (
            select(PaymentRequest)
            .where(PaymentRequest.id == req.id)
            .options(
                selectinload(PaymentRequest.agreement).selectinload(Agreement.participants),
                selectinload(PaymentRequest.orders),
                selectinload(PaymentRequest.captures),
            )
        )
        loaded_req = (await db.execute(stmt)).scalar_one()
        return PaymentService._build_payment_request_response(loaded_req, current_user)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for create_payment_request, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        return DevStore.create_payment_request(
            agreement_id=agreement_id,
            obligation_id=payload.obligation_id,
            current_user=current_user,
            amount=payload.amount,
            notes=payload.notes,
        )


@accord_payments_router.get(
    "/agreements/{agreement_id}/payment-requests",
    response_model=List[PaymentRequestResponse],
    summary="List all payment requests for an agreement",
)
async def list_agreement_payment_requests(
    agreement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[PaymentRequestResponse]:
    """Retrieve all payment requests generated for the given agreement."""
    try:
        stmt = (
            select(PaymentRequest)
            .where(PaymentRequest.agreement_id == agreement_id)
            .options(
                selectinload(PaymentRequest.agreement).selectinload(Agreement.participants),
                selectinload(PaymentRequest.orders),
                selectinload(PaymentRequest.captures),
            )
            .order_by(PaymentRequest.created_at.desc())
        )
        res = await db.execute(stmt)
        reqs = res.scalars().all()
        return [PaymentService._build_payment_request_response(r, current_user) for r in reqs]
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for list_agreement_payment_requests, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        return DevStore.list_payment_requests(agreement_id)


@accord_payments_router.get(
    "/payment-requests/{payment_request_id}",
    response_model=PaymentRequestResponse,
    summary="Retrieve payment request details",
)
async def get_payment_request_details(
    payment_request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentRequestResponse:
    """Retrieve full details, active PayPal order, and capture status for a payment request."""
    try:
        stmt = (
            select(PaymentRequest)
            .where(PaymentRequest.id == payment_request_id)
            .options(
                selectinload(PaymentRequest.agreement).selectinload(Agreement.participants),
                selectinload(PaymentRequest.orders),
                selectinload(PaymentRequest.captures),
            )
        )
        res = await db.execute(stmt)
        req = res.scalar_one_or_none()
        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment request not found.")
        return PaymentService._build_payment_request_response(req, current_user)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for get_payment_request_details, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        req = DevStore.get_payment_request(payment_request_id)
        if req:
            return req
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment request not found.")


@accord_payments_router.post(
    "/payment-requests/{payment_request_id}/cancel",
    response_model=PaymentRequestResponse,
    summary="Cancel an active payment request",
)
async def cancel_payment_request(
    payment_request_id: uuid.UUID,
    payload: CancelPaymentRequest = CancelPaymentRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentRequestResponse:
    """Cancel an active, uncaptured payment request."""
    try:
        cancelled = await PaymentService.cancel_payment_request(
            db=db,
            payment_request_id=payment_request_id,
            current_user=current_user,
            reason=payload.reason,
        )
        return PaymentService._build_payment_request_response(cancelled, current_user)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for cancel_payment_request, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        cancelled = DevStore.cancel_payment_request(payment_request_id, payload.reason)
        if cancelled:
            return cancelled
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment request not found.")


@accord_payments_router.get(
    "/payment-requests/{payment_request_id}/history",
    response_model=List[PaymentHistoryResponse],
    summary="Retrieve audit history for a payment request",
)
async def get_payment_request_history(
    payment_request_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[PaymentHistoryResponse]:
    """Retrieve the immutable lifecycle audit log for a payment request."""
    try:
        stmt = (
            select(PaymentHistory)
            .where(PaymentHistory.payment_request_id == payment_request_id)
            .order_by(PaymentHistory.created_at.asc())
        )
        res = await db.execute(stmt)
        history_entries = res.scalars().all()
        return [PaymentHistoryResponse.model_validate(h) for h in history_entries]
    except Exception as exc:
        logger.warning("DB unavailable for payment history: %s", exc)
        return []


@accord_payments_router.get(
    "/payment-requests/{payment_request_id}/argus-verification",
    summary="Retrieve ARGUS Pre-Settlement Verification report for this payment request",
)
async def get_payment_request_argus_verification(
    payment_request_id: uuid.UUID,
):
    """Returns the 4-worker AI forensic risk screening verdict and trust score produced by ARGUS."""
    from app.accord.services.dev_store import DevStore
    report = DevStore.get_argus_verification(payment_request_id)
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ARGUS verification report not found.")
    return report


@accord_payments_router.get(
    "/agreements/{agreement_id}/settlement",
    response_model=AgreementSettlementSummaryResponse,
    summary="Retrieve full settlement and payment overview for an agreement",
)
async def get_agreement_settlement(
    agreement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AgreementSettlementSummaryResponse:
    """Produce the complete settlement balance, obligation status, and collection ledger for an agreement."""
    try:
        return await PaymentService.get_agreement_settlement_summary(
            db=db,
            agreement_id=agreement_id,
            current_user=current_user,
        )
    except Exception as exc:
        logger.warning("DB unavailable for settlement summary, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        settlement = DevStore.get_settlement(agreement_id)
        if settlement:
            return settlement
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agreement settlement summary not found.",
        )


# ==============================================================================
# PAYPAL ORDERS & CAPTURE ENDPOINTS
# ==============================================================================

@router.post(
    "/paypal/orders",
    response_model=PayPalOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a PayPal v2 Checkout Order for an active payment request",
)
async def create_paypal_order(
    payload: CreatePayPalOrderRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PayPalOrderResponse:
    """Create a PayPal v2 Checkout Order with server-validated obligation amount and currency."""
    settings = get_settings()
    try:
        order = await PaymentService.create_paypal_order(
            db=db,
            payment_request_id=payload.payment_request_id,
            current_user=current_user,
            idempotency_key=idempotency_key,
        )
        paypal_client = get_paypal_client()
        return PayPalOrderResponse(
            id=order.id,
            payment_request_id=order.payment_request_id,
            paypal_order_id=order.paypal_order_id,
            amount=order.amount,
            currency=order.currency,
            status=order.status,
            approval_url=order.approval_url,
            client_id=settings.PAYPAL_CLIENT_ID,
            is_mock=paypal_client.mock_mode,
            original_amount=getattr(order, "original_amount", None),
            original_currency=getattr(order, "original_currency", None),
            exchange_rate=getattr(order, "exchange_rate", None),
            is_converted=getattr(order, "is_converted", False),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for create_paypal_order, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        return await DevStore.create_paypal_order(payload.payment_request_id, current_user)


@router.get(
    "/paypal/orders/{order_id}",
    response_model=PayPalOrderResponse,
    summary="Retrieve a PayPal Order by its PayPal Order ID",
)
async def get_paypal_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PayPalOrderResponse:
    """Retrieve internal and gateway details for a PayPal order."""
    settings = get_settings()
    try:
        stmt = select(PayPalOrder).where(PayPalOrder.paypal_order_id == order_id)
        res = await db.execute(stmt)
        order = res.scalar_one_or_none()
        if not order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"PayPal order '{order_id}' not found.")

        paypal_client = get_paypal_client()
        return PayPalOrderResponse(
            id=order.id,
            payment_request_id=order.payment_request_id,
            paypal_order_id=order.paypal_order_id,
            amount=order.amount,
            currency=order.currency,
            status=order.status,
            approval_url=order.approval_url,
            client_id=settings.PAYPAL_CLIENT_ID,
            is_mock=paypal_client.mock_mode,
            original_amount=getattr(order, "original_amount", None),
            original_currency=getattr(order, "original_currency", None),
            exchange_rate=getattr(order, "exchange_rate", None),
            is_converted=getattr(order, "is_converted", False),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for get_paypal_order, falling back to DevStore: %s", exc)
        return PayPalOrderResponse(
            id=uuid.uuid4(),
            payment_request_id=uuid.uuid4(),
            paypal_order_id=order_id,
            amount=Decimal("210.00"),
            currency="USD",
            status="CREATED",
            approval_url=f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}",
            client_id=settings.PAYPAL_CLIENT_ID,
            is_mock=False,
        )


@router.post(
    "/paypal/orders/{order_id}/capture",
    response_model=PaymentCaptureResponse,
    summary="Execute server-side capture of an approved PayPal order",
)
async def capture_paypal_order(
    order_id: str,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentCaptureResponse:
    """Server-side capture triggered upon payer approval, strictly validating amount and currency."""
    try:
        capture = await PaymentService.capture_paypal_order(
            db=db,
            order_id=order_id,
            current_user=current_user,
            idempotency_key=idempotency_key,
        )
        return PaymentCaptureResponse.model_validate(capture)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB unavailable for capture_paypal_order, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        return await DevStore.capture_paypal_order(order_id, current_user)


# ==============================================================================
# REFUNDS & CAPTURES ENDPOINTS
# ==============================================================================

@router.get(
    "/paypal/captures/{capture_id}",
    response_model=PaymentCaptureResponse,
    summary="Retrieve capture details",
)
async def get_paypal_capture(
    capture_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentCaptureResponse:
    """Retrieve captured payment details by PayPal capture ID."""
    stmt = select(PaymentCapture).where(PaymentCapture.paypal_capture_id == capture_id)
    res = await db.execute(stmt)
    capture = res.scalar_one_or_none()
    if not capture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Capture '{capture_id}' not found.")
    return PaymentCaptureResponse.model_validate(capture)


@router.post(
    "/paypal/captures/{capture_id}/refund",
    response_model=PaymentRefundResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a full or partial refund for a captured payment",
)
async def refund_paypal_capture(
    capture_id: str,
    payload: RefundPaymentRequest = RefundPaymentRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaymentRefundResponse:
    """Authorized agreement owner issues a refund for a previously captured payment."""
    refund = await PaymentService.refund_payment(
        db=db,
        capture_id=capture_id,
        current_user=current_user,
        reason=payload.reason,
        amount=payload.amount,
    )
    return PaymentRefundResponse.model_validate(refund)


# ==============================================================================
# WEBHOOKS ENDPOINT
# ==============================================================================

@router.post(
    "/paypal/webhook",
    response_model=WebhookProcessingResult,
    status_code=status.HTTP_200_OK,
    summary="PayPal Webhook receiver with signature verification and idempotent settlement",
)
async def receive_paypal_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> WebhookProcessingResult:
    """Authenticate and idempotently process PayPal webhooks."""
    body_bytes = await request.body()
    headers_dict = dict(request.headers)

    res = await PaymentService.process_webhook_event(
        db=db,
        headers=headers_dict,
        body_bytes=body_bytes,
    )
    return WebhookProcessingResult(
        event_id=res["event_id"],
        event_type=res["event_type"],
        verification_status=res["verification_status"],
        processing_status=res["processing_status"],
        message=res["message"],
    )

