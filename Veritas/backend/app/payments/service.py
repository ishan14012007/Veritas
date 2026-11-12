from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.accord.models.agreement import Agreement, AgreementParticipant
from app.accord.models.expense_split import ExpenseSplit, SplitShare
from app.accord.models.obligation import Obligation
from app.accord.services.calculator import ExpenseCalculator, ExpenseEntry
from app.core.config import get_settings
from app.core.models.audit import AuditLog
from app.core.models.user import User
from app.payments.models import (
    PaymentCapture,
    PaymentHistory,
    PaymentRefund,
    PaymentRequest,
    PaymentWebhookEvent,
    PayPalOrder,
)
from app.payments.paypal_client import get_paypal_client
from app.payments.schemas import (
    AgreementSettlementSummaryResponse,
    ObligationPaymentSummary,
    PaymentCaptureResponse,
    PaymentHistoryResponse,
    PaymentRefundResponse,
    PaymentRequestResponse,
    PayPalOrderResponse,
)

logger = logging.getLogger(__name__)


class PaymentService:
    """Core domain service orchestrating payment requests, PayPal checkout, server-side capture,
    refunds, webhooks, and agreement settlement reconciliation.
    """

    @classmethod
    def _compute_obligation_net_captured_from_requests(
        cls,
        obligation_id: uuid.UUID,
        payment_requests: List[PaymentRequest],
    ) -> Decimal:
        """Calculate net captured amount (total successful captures minus total successful refunds)
        for a specific obligation across all its associated payment requests.
        Accurately credits converted PayPal captures back to the original obligation currency.
        """
        total_net = Decimal("0.00")
        for req in payment_requests:
            if req.obligation_id != obligation_id:
                continue
            for cap in (req.captures or []):
                if cap.status in ("COMPLETED", "PARTIALLY_REFUNDED", "REFUNDED"):
                    cap_refunded = sum(
                        Decimal(str(r.amount)) for r in (cap.refunds or [])
                        if r.status == "COMPLETED"
                    )
                    net = max(Decimal("0.00"), Decimal(str(cap.amount)) - cap_refunded)
                    if cap.currency.upper() != req.currency.upper():
                        # Find corresponding PayPal order to get conversion proportion
                        ord_obj = next((o for o in (req.orders or []) if o.paypal_order_id == cap.paypal_order_id), None)
                        if ord_obj and ord_obj.amount > Decimal("0.00"):
                            ratio = min(Decimal("1.00"), net / ord_obj.amount)
                            total_net += (Decimal(str(req.amount)) * ratio).quantize(Decimal("0.01"))
                        else:
                            total_net += Decimal(str(req.amount)).quantize(Decimal("0.01"))
                    else:
                        total_net += net
        return total_net.quantize(Decimal("0.01"))

    @classmethod
    async def _compute_obligation_net_captured(
        cls,
        db: AsyncSession,
        obligation_id: uuid.UUID,
    ) -> Decimal:
        """Query DB directly to calculate net captured funds for an obligation,
        correctly reflecting currency conversion for unsupported PayPal currencies.
        """
        stmt = (
            select(PaymentCapture)
            .join(PaymentRequest, PaymentCapture.payment_request_id == PaymentRequest.id)
            .where(PaymentRequest.obligation_id == obligation_id)
            .options(
                selectinload(PaymentCapture.refunds),
                selectinload(PaymentCapture.payment_request).selectinload(PaymentRequest.orders),
            )
        )
        res = await db.execute(stmt)
        caps = res.scalars().all()
        total_net = Decimal("0.00")
        for cap in caps:
            if cap.status in ("COMPLETED", "PARTIALLY_REFUNDED", "REFUNDED"):
                cap_refunded = sum(
                    Decimal(str(r.amount)) for r in (cap.refunds or [])
                    if r.status == "COMPLETED"
                )
                net = max(Decimal("0.00"), Decimal(str(cap.amount)) - cap_refunded)
                req = cap.payment_request
                if req and cap.currency.upper() != req.currency.upper():
                    ord_obj = next((o for o in (req.orders or []) if o.paypal_order_id == cap.paypal_order_id), None)
                    if ord_obj and ord_obj.amount > Decimal("0.00"):
                        ratio = min(Decimal("1.00"), net / ord_obj.amount)
                        total_net += (Decimal(str(req.amount)) * ratio).quantize(Decimal("0.01"))
                    else:
                        total_net += Decimal(str(req.amount)).quantize(Decimal("0.01"))
                else:
                    total_net += net
        return total_net.quantize(Decimal("0.01"))

    @classmethod
    async def create_payment_request(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        obligation_id: uuid.UUID,
        current_user: User,
        amount: Optional[Decimal] = None,
        notes: Optional[str] = None,
    ) -> PaymentRequest:
        """Validate payment eligibility and create a payment request against a confirmed obligation."""
        settings = get_settings()

        # Reconcile obligations against expense splits first
        await cls.reconcile_agreement_settlement_obligations(db, agreement_id)

        # 1. Retrieve Agreement with participants
        stmt_agr = (
            select(Agreement)
            .where(Agreement.id == agreement_id)
            .options(
                selectinload(Agreement.participants),
                selectinload(Agreement.obligations),
            )
        )
        res_agr = await db.execute(stmt_agr)
        agreement = res_agr.scalar_one_or_none()

        if not agreement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agreement {agreement_id} not found.",
            )

        # 2. Enforce Agreement Confirmation Requirement
        # Under Section 4: A payment request can ONLY be created if agreement is CONFIRMED and every participant accepted
        if agreement.status != "CONFIRMED" or not agreement.is_confirmed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot create payment request: Agreement status is '{agreement.status}'. Agreement must be CONFIRMED with mutual consensus before settlement.",
            )

        # Verify all participants have accepted current version
        unaccepted_parts = [
            p.name for p in agreement.participants
            if p.consent_status != "ACCEPTED" or p.responded_version != agreement.version
        ]
        if unaccepted_parts:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot create payment request: Not all participants have accepted Version {agreement.version}. Pending: {', '.join(unaccepted_parts)}.",
            )

        # 3. Retrieve and Validate Obligation
        stmt_ob = select(Obligation).where(Obligation.id == obligation_id)
        res_ob = await db.execute(stmt_ob)
        obligation = res_ob.scalar_one_or_none()

        if not obligation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Obligation {obligation_id} not found.",
            )

        if obligation.agreement_id != agreement.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The specified obligation does not belong to this agreement.",
            )

        ob_amount = (obligation.amount or Decimal("0.00")).quantize(Decimal("0.01"))
        if ob_amount <= Decimal("0.00"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Obligation must have an explicitly positive monetary amount to create a payment request.",
            )

        # 4. Check if obligation is already settled or fulfilled
        net_captured = await cls._compute_obligation_net_captured(db, obligation.id)
        remaining_balance = max(Decimal("0.00"), ob_amount - net_captured).quantize(Decimal("0.01"))

        if remaining_balance <= Decimal("0.00") or obligation.status in ("FULFILLED", "SETTLED"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Obligation '{obligation.title}' is already fully settled (${net_captured} captured).",
            )

        if amount is not None:
            req_amount = Decimal(str(amount)).quantize(Decimal("0.01"))
            if req_amount <= Decimal("0.00"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Requested payment amount must be positive.",
                )
            if req_amount > remaining_balance:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Requested payment amount (${req_amount}) exceeds remaining obligation balance (${remaining_balance}).",
                )
        else:
            req_amount = remaining_balance

        # 5. Validate Debtors, Creditors, and Monetary Values
        debtor_name = obligation.debtor_name
        creditor_name = obligation.creditor_name
        if not creditor_name and agreement.participants:
            for p in agreement.participants:
                if p.name.strip().lower() != (debtor_name or "").strip().lower():
                    creditor_name = p.name
                    break

        if not debtor_name or not creditor_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Obligation is missing debtor or creditor identification and cannot be settled via checkout.",
            )

        currency = (obligation.currency or "USD").upper()

        # 6. Check existing PaymentRequests for this obligation
        stmt_existing = (
            select(PaymentRequest)
            .where(
                PaymentRequest.obligation_id == obligation.id,
                PaymentRequest.status.in_(["PENDING", "APPROVED", "PROCESSING"]),
            )
            .options(
                selectinload(PaymentRequest.orders),
                selectinload(PaymentRequest.captures),
            )
        )
        res_existing = await db.execute(stmt_existing)
        existing_req = res_existing.scalar_one_or_none()

        if existing_req:
            # Idempotently return existing unpaid payment request
            return existing_req

        # 7. Authorization Check:
        # User must be the debtor participant's bound account, agreement owner, or creditor participant
        debtor_part = next(
            (p for p in agreement.participants if p.name.strip().lower() == obligation.debtor_name.strip().lower()),
            None,
        )
        creditor_part = next(
            (p for p in agreement.participants if p.name.strip().lower() == obligation.creditor_name.strip().lower()),
            None,
        )

        is_owner = agreement.owner_id == current_user.id
        is_debtor = debtor_part and debtor_part.user_id == current_user.id
        is_creditor = creditor_part and creditor_part.user_id == current_user.id

        if not (is_owner or is_debtor or is_creditor):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to create a payment request for this obligation.",
            )

        # 8. Create PaymentRequest
        receiver_account = getattr(settings, "PAYPAL_RECEIVER_ACCOUNT", "merchant_sandbox@veritas.local")

        payment_request = PaymentRequest(
            agreement_id=agreement.id,
            agreement_version=agreement.version,
            obligation_id=obligation.id,
            debtor_participant_id=debtor_part.id if debtor_part else None,
            creditor_participant_id=creditor_part.id if creditor_part else None,
            debtor_name=debtor_name,
            creditor_name=creditor_name,
            receiver_merchant_account=receiver_account,
            amount=req_amount,
            currency=currency,
            status="PENDING",
            due_date=obligation.due_date,
            created_by_user_id=current_user.id,
        )
        db.add(payment_request)
        await db.flush()

        # Audit record in PaymentHistory
        history_entry = PaymentHistory(
            payment_request_id=payment_request.id,
            action="REQUEST_CREATED",
            from_status=None,
            to_status="PENDING",
            performed_by_user_id=current_user.id,
            details={
                "amount": str(payment_request.amount),
                "currency": payment_request.currency,
                "obligation_title": obligation.title,
                "notes": notes,
            },
        )
        db.add(history_entry)

        # Audit log
        audit = AuditLog(
            user_id=current_user.id,
            action="PAYMENT_REQUEST_CREATED",
            resource_type="payment_request",
            resource_id=str(payment_request.id),
            changes={
                "agreement_id": str(agreement.id),
                "obligation_id": str(obligation.id),
                "amount": str(payment_request.amount),
                "currency": payment_request.currency,
            },
        )
        db.add(audit)

        await db.commit()
        await db.refresh(payment_request)
        return payment_request

    @classmethod
    async def create_paypal_order(
        cls,
        db: AsyncSession,
        payment_request_id: uuid.UUID,
        current_user: User,
        idempotency_key: Optional[str] = None,
    ) -> PayPalOrder:
        """Create a PayPal v2 Checkout Order for an active payment request."""
        stmt = (
            select(PaymentRequest)
            .where(PaymentRequest.id == payment_request_id)
            .options(
                selectinload(PaymentRequest.agreement).selectinload(Agreement.participants),
                selectinload(PaymentRequest.obligation),
                selectinload(PaymentRequest.orders),
            )
        )
        res = await db.execute(stmt)
        req = res.scalar_one_or_none()

        if not req:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment request {payment_request_id} not found.",
            )

        if req.status in ("COMPLETED", "CANCELLED", "REFUNDED"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot create PayPal order: Payment request is already {req.status}.",
            )

        # Check authorization (debtor or agreement owner)
        debtor_part = next(
            (p for p in req.agreement.participants if p.id == req.debtor_participant_id),
            None,
        )
        is_debtor = debtor_part and debtor_part.user_id == current_user.id
        is_owner = req.agreement.owner_id == current_user.id
        if not (is_debtor or is_owner):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the designated debtor or agreement creator can initiate PayPal checkout.",
            )

        # Call Currency Conversion Layer to guarantee PayPal currency compatibility
        from app.payments.currency_service import get_currency_service
        currency_service = get_currency_service()
        conversion = await currency_service.convert_for_paypal(
            amount=req.amount,
            currency=req.currency,
        )

        # Call PayPal Orders API
        paypal_client = get_paypal_client()
        order_key = idempotency_key or str(uuid.uuid4())

        description = f"VERITAS: {req.obligation.title if req.obligation else 'Settlement'}"
        if conversion.is_converted:
            description = f"{description} ({conversion.original_currency} {conversion.original_amount:.2f})"[:127]

        order_data = await paypal_client.create_order(
            amount=conversion.paypal_amount,
            currency=conversion.paypal_currency,
            reference_id=str(req.id),
            custom_id=str(req.obligation_id),
            description=description,
            idempotency_key=order_key,
            payee_email=req.receiver_merchant_account,
        )

        paypal_order = PayPalOrder(
            payment_request_id=req.id,
            paypal_order_id=order_data["id"],
            amount=conversion.paypal_amount,
            currency=conversion.paypal_currency,
            status=order_data["status"],
            approval_url=order_data.get("approval_url"),
            custom_id=str(req.obligation_id),
            reference_id=str(req.id),
        )
        db.add(paypal_order)

        # Update PaymentRequest
        prev_status = req.status
        req.paypal_order_id = order_data["id"]
        req.status = "PENDING"

        history = PaymentHistory(
            payment_request_id=req.id,
            action="ORDER_CREATED",
            from_status=prev_status,
            to_status="PENDING",
            performed_by_user_id=current_user.id,
            details={
                "paypal_order_id": order_data["id"],
                "approval_url": order_data.get("approval_url"),
                "paypal_amount": str(conversion.paypal_amount),
                "paypal_currency": conversion.paypal_currency,
                "original_amount": str(conversion.original_amount),
                "original_currency": conversion.original_currency,
                "exchange_rate": str(conversion.exchange_rate),
                "is_converted": conversion.is_converted,
            },
        )
        db.add(history)

        # Attach conversion metadata dynamically for response construction
        paypal_order.original_amount = conversion.original_amount
        paypal_order.original_currency = conversion.original_currency
        paypal_order.exchange_rate = conversion.exchange_rate
        paypal_order.is_converted = conversion.is_converted

        await db.commit()
        await db.refresh(paypal_order)
        return paypal_order

    @classmethod
    async def capture_paypal_order(
        cls,
        db: AsyncSession,
        order_id: str,
        current_user: User,
        idempotency_key: Optional[str] = None,
    ) -> PaymentCapture:
        """Execute server-side capture of an approved PayPal Order with strict amount, currency,
        and ownership validation.
        """
        # 1. Retrieve the PayPalOrder and PaymentRequest
        stmt = (
            select(PayPalOrder)
            .where(PayPalOrder.paypal_order_id == order_id)
            .options(
                selectinload(PayPalOrder.payment_request).selectinload(PaymentRequest.agreement).selectinload(Agreement.participants),
                selectinload(PayPalOrder.payment_request).selectinload(PaymentRequest.obligation),
                selectinload(PayPalOrder.payment_request).selectinload(PaymentRequest.captures),
            )
        )
        res = await db.execute(stmt)
        paypal_order = res.scalar_one_or_none()

        if not paypal_order or not paypal_order.payment_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order '{order_id}' is not associated with any active VERITAS payment request.",
            )

        req = paypal_order.payment_request
        obligation = req.obligation

        # 2. Check Idempotency: If already captured, return existing capture
        stmt_cap = select(PaymentCapture).where(PaymentCapture.paypal_order_id == order_id)
        res_cap = await db.execute(stmt_cap)
        existing_cap = res_cap.scalar_one_or_none()
        if existing_cap:
            return existing_cap

        # 3. Authorization check
        debtor_part = next(
            (p for p in req.agreement.participants if p.id == req.debtor_participant_id),
            None,
        )
        is_debtor = debtor_part and debtor_part.user_id == current_user.id
        is_owner = req.agreement.owner_id == current_user.id
        if not (is_debtor or is_owner):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to capture payment for this request.",
            )

        # 4. Check whether payment request or obligation is already settled
        if req.status == "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment request has already been completed.",
            )

        if obligation and obligation.status in ("FULFILLED", "SETTLED"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Obligation is already marked as {obligation.status}.",
            )

        # 5. Call PayPal Server-Side Capture API
        paypal_client = get_paypal_client()
        cap_key = idempotency_key or str(uuid.uuid4())

        capture_data = await paypal_client.capture_order(order_id, idempotency_key=cap_key)

        # 6. Verify Amount and Currency against database record
        captured_amount_str = capture_data.get("amount", "0")
        captured_currency = capture_data.get("currency", "USD").upper()
        captured_amount = Decimal(captured_amount_str)

        # Quantize to 2 decimal places for comparison
        expected_amount = Decimal(paypal_order.amount).quantize(Decimal("0.01"))
        actual_amount = captured_amount.quantize(Decimal("0.01"))

        if actual_amount != expected_amount:
            logger.critical(
                f"PAYMENT SECURITY ALERT: Amount mismatch! Expected {expected_amount}, received {actual_amount} for Order {order_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security error: Captured amount ({actual_amount}) does not match authorized obligation amount ({expected_amount}).",
            )

        if captured_currency != paypal_order.currency.upper():
            logger.critical(
                f"PAYMENT SECURITY ALERT: Currency mismatch! Expected {paypal_order.currency}, received {captured_currency} for Order {order_id}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Security error: Captured currency ({captured_currency}) does not match authorized order currency ({paypal_order.currency}).",
            )

        # 7. Persist PaymentCapture
        fee_val = Decimal(capture_data["fee"]) if capture_data.get("fee") else Decimal("0.0000")
        net_val = Decimal(capture_data["net_amount"]) if capture_data.get("net_amount") else (actual_amount - fee_val)

        captured_at_dt = datetime.now(timezone.utc)
        if capture_data.get("captured_at"):
            try:
                captured_at_dt = datetime.fromisoformat(capture_data["captured_at"].replace("Z", "+00:00"))
            except Exception:
                pass

        payment_capture = PaymentCapture(
            payment_request_id=req.id,
            payment_request=req,
            paypal_order_id=order_id,
            paypal_capture_id=capture_data["id"],
            amount=actual_amount,
            currency=captured_currency,
            status=capture_data.get("status", "COMPLETED"),
            paypal_fee=fee_val,
            net_amount=net_val,
            captured_at=captured_at_dt,
        )
        db.add(payment_capture)
        if hasattr(req, "captures") and req.captures is not None and payment_capture not in req.captures:
            req.captures.append(payment_capture)

        # 8. Update statuses
        prev_status = req.status
        req.status = "COMPLETED"
        paypal_order.status = "COMPLETED"
        await db.flush()

        if obligation:
            total_net = await cls._compute_obligation_net_captured(db, obligation.id)
            ob_amount = (obligation.amount or Decimal("0.00")).quantize(Decimal("0.01"))
            if ob_amount > Decimal("0.00") and total_net >= ob_amount:
                obligation.status = "FULFILLED"
            else:
                obligation.status = "PENDING"

        # 9. Audit History
        history = PaymentHistory(
            payment_request_id=req.id,
            action="CAPTURE_SUCCEEDED",
            from_status=prev_status,
            to_status="COMPLETED",
            performed_by_user_id=current_user.id,
            details={
                "paypal_capture_id": capture_data["id"],
                "captured_amount": str(actual_amount),
                "currency": captured_currency,
                "fee": str(fee_val),
                "net": str(net_val),
            },
        )
        db.add(history)

        audit = AuditLog(
            user_id=current_user.id,
            action="PAYMENT_CAPTURED",
            resource_type="payment_request",
            resource_id=str(req.id),
            changes={
                "capture_id": capture_data["id"],
                "order_id": order_id,
                "amount": str(actual_amount),
                "currency": captured_currency,
                "obligation_id": str(obligation.id) if obligation else None,
            },
        )
        db.add(audit)

        await db.commit()
        await db.refresh(payment_capture)
        return payment_capture

    @classmethod
    async def cancel_payment_request(
        cls,
        db: AsyncSession,
        payment_request_id: uuid.UUID,
        current_user: User,
        reason: Optional[str] = None,
    ) -> PaymentRequest:
        """Cancel an active, uncaptured payment request."""
        stmt = (
            select(PaymentRequest)
            .where(PaymentRequest.id == payment_request_id)
            .options(
                selectinload(PaymentRequest.agreement),
                selectinload(PaymentRequest.orders),
            )
        )
        res = await db.execute(stmt)
        req = res.scalar_one_or_none()

        if not req:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment request {payment_request_id} not found.",
            )

        if req.status == "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot cancel a completed payment request. Issue a refund instead.",
            )

        if req.status == "CANCELLED":
            return req

        is_owner = req.agreement.owner_id == current_user.id
        is_creator = req.created_by_user_id == current_user.id
        if not (is_owner or is_creator):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to cancel this payment request.",
            )

        prev_status = req.status
        req.status = "CANCELLED"

        history = PaymentHistory(
            payment_request_id=req.id,
            action="CANCELLED",
            from_status=prev_status,
            to_status="CANCELLED",
            performed_by_user_id=current_user.id,
            details={"reason": reason},
        )
        db.add(history)

        await db.commit()
        await db.refresh(req)
        return req

    @classmethod
    async def refund_payment(
        cls,
        db: AsyncSession,
        capture_id: str,
        current_user: User,
        reason: Optional[str] = None,
        amount: Optional[Decimal] = None,
    ) -> PaymentRefund:
        """Issue a refund against a server-side captured payment."""
        stmt = (
            select(PaymentCapture)
            .where(PaymentCapture.paypal_capture_id == capture_id)
            .options(
                selectinload(PaymentCapture.payment_request).selectinload(PaymentRequest.agreement),
                selectinload(PaymentCapture.payment_request).selectinload(PaymentRequest.obligation),
                selectinload(PaymentCapture.refunds),
            )
        )
        res = await db.execute(stmt)
        capture = res.scalar_one_or_none()

        if not capture or not capture.payment_request:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Payment capture '{capture_id}' not found.",
            )

        req = capture.payment_request

        # Authorization: Agreement owner only
        is_owner = req.agreement.owner_id == current_user.id
        if not is_owner:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the agreement creator can authorize and issue refunds.",
            )

        refund_amount = amount or capture.amount
        if refund_amount <= Decimal("0.00"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Refund amount must be positive.")

        if refund_amount > capture.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Refund amount ({refund_amount}) cannot exceed captured amount ({capture.amount}).",
            )

        paypal_client = get_paypal_client()
        refund_res = await paypal_client.refund_capture(
            capture_id=capture.paypal_capture_id,
            amount=refund_amount,
            currency=capture.currency,
            note=reason,
        )

        payment_refund = PaymentRefund(
            payment_capture_id=capture.id,
            payment_capture=capture,
            payment_request_id=req.id,
            payment_request=req,
            paypal_refund_id=refund_res["id"],
            amount=refund_amount,
            currency=capture.currency,
            status=refund_res.get("status", "COMPLETED"),
            reason=reason,
            refunded_by_user_id=current_user.id,
        )
        db.add(payment_refund)
        if hasattr(capture, "refunds") and capture.refunds is not None and payment_refund not in capture.refunds:
            capture.refunds.append(payment_refund)
        if hasattr(req, "refunds") and req.refunds is not None and payment_refund not in req.refunds:
            req.refunds.append(payment_refund)

        prev_status = req.status
        is_full_capture_refund = refund_amount >= capture.amount
        capture.status = "REFUNDED" if is_full_capture_refund else "PARTIALLY_REFUNDED"
        await db.flush()

        # Recompute total net captured funds for this obligation
        total_net = await cls._compute_obligation_net_captured(db, req.obligation_id)

        if total_net <= Decimal("0.00"):
            new_status = "REFUNDED"
        else:
            new_status = "PARTIALLY_REFUNDED"
        req.status = new_status

        # If net captured drops below obligation amount (full or partial refund), revert to PENDING
        if req.obligation:
            ob_amount = (req.obligation.amount or Decimal("0.00")).quantize(Decimal("0.01"))
            if ob_amount > Decimal("0.00") and total_net >= ob_amount:
                req.obligation.status = "FULFILLED"
            else:
                req.obligation.status = "PENDING"

        history = PaymentHistory(
            payment_request_id=req.id,
            action="REFUND_ISSUED",
            from_status=prev_status,
            to_status=new_status,
            performed_by_user_id=current_user.id,
            details={
                "paypal_refund_id": refund_res["id"],
                "refunded_amount": str(refund_amount),
                "is_full_refund": is_full_capture_refund,
                "reason": reason,
            },
        )
        db.add(history)

        await db.commit()
        await db.refresh(payment_refund)
        return payment_refund

    @classmethod
    async def process_webhook_event(
        cls,
        db: AsyncSession,
        headers: Dict[str, str],
        body_bytes: bytes,
    ) -> Dict[str, Any]:
        """Authenticate and idempotently process PayPal webhooks, reconciling capture and settlement."""
        paypal_client = get_paypal_client()
        settings = get_settings()

        # 1. Parse JSON body
        try:
            event = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON webhook body.")

        event_id = event.get("id")
        event_type = event.get("event_type")
        if not event_id or not event_type:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing event ID or event type.")

        # 2. Check Idempotency: Has event already been received?
        stmt_exist = select(PaymentWebhookEvent).where(PaymentWebhookEvent.paypal_event_id == event_id)
        res_exist = await db.execute(stmt_exist)
        existing_event = res_exist.scalar_one_or_none()

        if existing_event and existing_event.processing_status == "PROCESSED":
            return {
                "event_id": event_id,
                "event_type": event_type,
                "verification_status": existing_event.verification_status,
                "processing_status": "PROCESSED",
                "message": "Webhook event was previously processed (idempotent).",
            }

        # 3. Verify Signature
        is_verified = await paypal_client.verify_webhook_signature(
            headers=headers,
            body_bytes=body_bytes,
            webhook_id=settings.PAYPAL_WEBHOOK_ID,
        )

        verification_status = "VERIFIED" if is_verified else "FAILED"
        if not is_verified:
            logger.warning(f"PayPal webhook signature verification failed for event {event_id}")
            # Record failed verification event
            failed_record = PaymentWebhookEvent(
                paypal_event_id=event_id,
                event_type=event_type,
                resource_type=event.get("resource_type"),
                verification_status="FAILED",
                processing_status="FAILED",
                payload=event,
                error_message="Invalid PayPal transmission signature.",
            )
            db.add(failed_record)
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PayPal webhook signature.",
            )

        # 4. Record event
        webhook_record = existing_event or PaymentWebhookEvent(
            paypal_event_id=event_id,
            event_type=event_type,
            resource_type=event.get("resource_type"),
            verification_status="VERIFIED",
            processing_status="PENDING",
            payload=event,
        )
        if not existing_event:
            db.add(webhook_record)
        await db.flush()

        # 5. Process relevant event types
        resource = event.get("resource", {})
        resource_id = resource.get("id")
        webhook_record.resource_id = resource_id

        if event_type == "CHECKOUT.ORDER.APPROVED":
            # Order was approved by payer
            stmt_order = select(PayPalOrder).where(PayPalOrder.paypal_order_id == resource_id)
            res_ord = await db.execute(stmt_order)
            ord_obj = res_ord.scalar_one_or_none()
            if ord_obj:
                ord_obj.status = "APPROVED"
                stmt_req = select(PaymentRequest).where(PaymentRequest.id == ord_obj.payment_request_id)
                req_obj = (await db.execute(stmt_req)).scalar_one_or_none()
                if req_obj and req_obj.status != "COMPLETED":
                    req_obj.status = "APPROVED"
                    history = PaymentHistory(
                        payment_request_id=req_obj.id,
                        action="PAYER_APPROVED",
                        from_status="PENDING",
                        to_status="APPROVED",
                        details={"paypal_order_id": resource_id, "event_id": event_id},
                    )
                    db.add(history)

        elif event_type == "PAYMENT.CAPTURE.COMPLETED":
            # Reconcile capture completion
            order_id = None
            # Check supplementary_data or links for order id
            supp = resource.get("supplementary_data", {})
            if "related_ids" in supp and "order_id" in supp["related_ids"]:
                order_id = supp["related_ids"]["order_id"]

            if not order_id and "custom_id" in resource:
                # Custom ID might be obligation ID
                pass

            # Search by capture ID or order ID
            stmt_cap = (
                select(PaymentCapture)
                .where(PaymentCapture.paypal_capture_id == resource_id)
                .options(selectinload(PaymentCapture.payment_request).selectinload(PaymentRequest.obligation))
            )
            res_cap = await db.execute(stmt_cap)
            existing_cap = res_cap.scalar_one_or_none()

            if existing_cap:
                req = existing_cap.payment_request
                if req and req.status != "COMPLETED":
                    req.status = "COMPLETED"
                    history = PaymentHistory(
                        payment_request_id=req.id,
                        action="WEBHOOK_CONFIRMED",
                        from_status=req.status,
                        to_status="COMPLETED",
                        details={"event_id": event_id, "capture_id": resource_id},
                    )
                    db.add(history)
                if req and req.obligation:
                    total_net = await cls._compute_obligation_net_captured(db, req.obligation_id)
                    ob_amount = (req.obligation.amount or Decimal("0.00")).quantize(Decimal("0.01"))
                    if ob_amount > Decimal("0.00") and total_net >= ob_amount:
                        req.obligation.status = "FULFILLED"
                    else:
                        req.obligation.status = "PENDING"

        elif event_type in ("PAYMENT.CAPTURE.REFUNDED", "PAYMENT.CAPTURE.REVERSED"):
            stmt_cap = (
                select(PaymentCapture)
                .where(PaymentCapture.paypal_capture_id == resource_id)
                .options(selectinload(PaymentCapture.payment_request).selectinload(PaymentRequest.obligation))
            )
            res_cap = await db.execute(stmt_cap)
            existing_cap = res_cap.scalar_one_or_none()
            if existing_cap and existing_cap.payment_request:
                req = existing_cap.payment_request
                total_net = await cls._compute_obligation_net_captured(db, req.obligation_id)
                if total_net <= Decimal("0.00"):
                    req.status = "REFUNDED"
                else:
                    req.status = "PARTIALLY_REFUNDED"
                if req.obligation:
                    ob_amount = (req.obligation.amount or Decimal("0.00")).quantize(Decimal("0.01"))
                    if ob_amount > Decimal("0.00") and total_net >= ob_amount:
                        req.obligation.status = "FULFILLED"
                    else:
                        req.obligation.status = "PENDING"
                history = PaymentHistory(
                    payment_request_id=req.id,
                    action="WEBHOOK_REFUND_CONFIRMED",
                    from_status=req.status,
                    to_status=req.status,
                    details={"event_id": event_id, "capture_id": resource_id},
                )
                db.add(history)

        elif event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.DECLINED"):
            # Mark payment request as failed
            stmt_cap = (
                select(PaymentCapture)
                .where(PaymentCapture.paypal_capture_id == resource_id)
                .options(selectinload(PaymentCapture.payment_request))
            )
            cap = (await db.execute(stmt_cap)).scalar_one_or_none()
            if cap and cap.payment_request:
                req = cap.payment_request
                req.status = "FAILED"
                history = PaymentHistory(
                    payment_request_id=req.id,
                    action="CAPTURE_FAILED",
                    from_status=req.status,
                    to_status="FAILED",
                    details={"event_id": event_id, "reason": resource.get("status_details", {})},
                )
                db.add(history)

        webhook_record.processing_status = "PROCESSED"
        webhook_record.processed_at = datetime.now(timezone.utc)
        await db.commit()

        return {
            "event_id": event_id,
            "event_type": event_type,
            "verification_status": "VERIFIED",
            "processing_status": "PROCESSED",
            "message": "Webhook processed successfully.",
        }

    @classmethod
    async def reconcile_agreement_settlement_obligations(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
    ) -> List[Obligation]:
        """Ensure all deterministic settlement transfers calculated from expense splits
        are represented by exactly one structured payable obligation in the database.
        Idempotent: will not create duplicate obligations if already present.
        Preserves existing payment captures and refunds.
        """
        stmt = (
            select(Agreement)
            .where(Agreement.id == agreement_id)
            .options(
                selectinload(Agreement.obligations),
                selectinload(Agreement.participants),
                selectinload(Agreement.expense_splits).selectinload(ExpenseSplit.shares),
            )
        )
        res = await db.execute(stmt)
        agreement = res.scalar_one_or_none()
        if not agreement:
            return []

        if not agreement.expense_splits:
            return list(agreement.obligations)

        es = agreement.expense_splits[0]
        if not es.shares:
            return list(agreement.obligations)

        # Re-compute deterministic settlement transfers from expense split shares
        expenses = [
            ExpenseEntry(
                payer_name=sh.participant_name,
                amount=sh.paid_amount,
                description="Shared Expense",
            )
            for sh in es.shares
            if sh.paid_amount > Decimal("0.00")
        ]
        participants = [sh.participant_name for sh in es.shares]

        if not expenses or not participants:
            return list(agreement.obligations)

        calc_result = ExpenseCalculator.calculate_split(
            expenses=expenses,
            participants=participants,
            split_method=es.split_method or "EQUAL",
            currency=es.currency or agreement.currency or "USD",
        )

        modified = False
        for tr in calc_result.settlement_transfers:
            debtor_clean = tr.from_participant.strip()
            creditor_clean = tr.to_participant.strip()
            expected_amt = Decimal(str(round(float(tr.amount), 2)))

            # Match existing obligation for this debtor
            existing = next(
                (
                    o for o in agreement.obligations
                    if o.debtor_name and o.debtor_name.strip().lower() == debtor_clean.lower()
                    and (
                        not o.creditor_name
                        or o.creditor_name.strip().lower() == creditor_clean.lower()
                    )
                ),
                None,
            )

            if existing:
                # Backfill missing creditor or amount if unset
                if not existing.creditor_name:
                    existing.creditor_name = creditor_clean
                    modified = True
                if existing.amount is None or existing.amount <= Decimal("0.00"):
                    existing.amount = expected_amt
                    modified = True
            else:
                # Create missing obligation
                currency_sym = "₹" if calc_result.currency == "INR" else ("€" if calc_result.currency == "EUR" else "$")
                new_ob = Obligation(
                    agreement_id=agreement.id,
                    analysis_id=agreement.analysis_id,
                    title=f"{debtor_clean}'s Settlement Transfer",
                    description=f"{debtor_clean} owes {creditor_clean} {currency_sym}{expected_amt} ({calc_result.currency}) to balance shared expenses.",
                    debtor_name=debtor_clean,
                    creditor_name=creditor_clean,
                    amount=expected_amt,
                    currency=calc_result.currency,
                    status="PENDING",
                    is_freelance_milestone=False,
                    condition=f"Settlement of {es.split_method} expense split",
                    evidence_quote=f"Calculated settlement transfer: {debtor_clean} owes {creditor_clean} {currency_sym}{expected_amt}.",
                )
                db.add(new_ob)
                agreement.obligations.append(new_ob)
                modified = True

        if modified:
            await db.commit()
            await db.refresh(agreement)

        return list(agreement.obligations)

    @classmethod
    async def get_agreement_settlement_summary(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        current_user: User,
    ) -> AgreementSettlementSummaryResponse:
        """Produce the comprehensive settlement overview for an agreement."""
        # First reconcile obligations against expense splits so all payable transfers are present
        await cls.reconcile_agreement_settlement_obligations(db, agreement_id)
        stmt = (
            select(Agreement)
            .where(Agreement.id == agreement_id)
            .options(
                selectinload(Agreement.participants),
                selectinload(Agreement.obligations),
                selectinload(Agreement.payment_requests).selectinload(PaymentRequest.orders),
                selectinload(Agreement.payment_requests).selectinload(PaymentRequest.captures).selectinload(PaymentCapture.refunds),
                selectinload(Agreement.payment_requests).selectinload(PaymentRequest.refunds),
            )
        )
        res = await db.execute(stmt)
        agreement = res.scalar_one_or_none()

        if not agreement:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agreement {agreement_id} not found.",
            )

        # Check authorization (participant or owner)
        is_owner = agreement.owner_id == current_user.id
        is_participant = any(p.user_id == current_user.id for p in agreement.participants)
        if not (is_owner or is_participant):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to view settlement details for this agreement.",
            )

        is_consensus = agreement.status == "CONFIRMED" and agreement.is_confirmed

        # Calculate totals from actual obligations and verifiable capture/refund records
        total_obligations = Decimal("0.00")
        total_completed = Decimal("0.00")
        total_pending = Decimal("0.00")
        total_failed = Decimal("0.00")

        currency = agreement.currency or (agreement.obligations and agreement.obligations[0].currency) or "USD"

        # Calculate pending and failed amounts from payment requests
        for req in agreement.payment_requests:
            if req.status in ("PENDING", "APPROVED", "PROCESSING"):
                total_pending += req.amount
            elif req.status in ("FAILED", "CANCELLED"):
                total_failed += req.amount

        obligation_summaries: List[ObligationPaymentSummary] = []
        payable_obligations_count = 0
        settled_obligations_count = 0

        for ob in agreement.obligations:
            ob_amount = (ob.amount or Decimal("0.00")).quantize(Decimal("0.01"))
            total_obligations += ob_amount
            if ob_amount > Decimal("0.00"):
                payable_obligations_count += 1

            # Compute net captured funds from all successful captures and refunds
            net_captured = await cls._compute_obligation_net_captured(db, ob.id)
            settled_amount = min(ob_amount, net_captured).quantize(Decimal("0.01"))
            outstanding_amount = max(Decimal("0.00"), ob_amount - net_captured).quantize(Decimal("0.01"))

            # An obligation is settled ONLY when full amount is successfully captured
            is_settled = bool(ob_amount > Decimal("0.00") and net_captured >= ob_amount)
            if is_settled:
                settled_obligations_count += 1

            total_completed += settled_amount

            # Find latest or active payment request for this obligation
            ob_reqs = [r for r in agreement.payment_requests if r.obligation_id == ob.id]
            active_req = next((r for r in ob_reqs if r.status in ("PENDING", "APPROVED", "PROCESSING")), None)
            latest_req = active_req or (ob_reqs[0] if ob_reqs else None)
            if latest_req and not latest_req.captures:
                stmt_c = (
                    select(PaymentCapture)
                    .where(PaymentCapture.payment_request_id == latest_req.id)
                    .order_by(PaymentCapture.created_at.desc())
                )
                latest_req.captures = list((await db.execute(stmt_c)).scalars().all())

            # Check payment eligibility:
            # - Agreement must be mutually confirmed
            # - Obligation must have positive remaining outstanding amount
            is_eligible = bool(is_consensus and not is_settled and outstanding_amount > Decimal("0.00"))
            ineligibility_reason = None
            if not is_consensus:
                ineligibility_reason = "Agreement is not mutually confirmed."
            elif is_settled:
                ineligibility_reason = "Obligation is already settled."
            elif outstanding_amount <= Decimal("0.00"):
                ineligibility_reason = "Obligation has no payable amount."

            req_resp = None
            if latest_req:
                req_resp = cls._build_payment_request_response(latest_req, current_user, agreement)

            obligation_summaries.append(
                ObligationPaymentSummary(
                    obligation_id=ob.id,
                    title=ob.title,
                    description=ob.description,
                    debtor_name=ob.debtor_name,
                    creditor_name=ob.creditor_name,
                    amount=ob_amount,
                    currency=ob.currency or currency,
                    obligation_status=ob.status,
                    is_settled=is_settled,
                    settled_amount=settled_amount,
                    outstanding_amount=outstanding_amount,
                    is_eligible_for_payment=is_eligible,
                    ineligibility_reason=ineligibility_reason,
                    payment_request=req_resp,
                )
            )

        outstanding = max(Decimal("0.00"), total_obligations - total_completed).quantize(Decimal("0.01"))

        # Settlement status:
        # FULLY_SETTLED only when EVERY payable obligation is settled
        # PARTIALLY_SETTLED if some funds captured but remaining balance outstanding
        # UNSETTLED otherwise
        if payable_obligations_count > 0 and settled_obligations_count == payable_obligations_count:
            settlement_status = "FULLY_SETTLED"
        elif total_completed > Decimal("0.00"):
            settlement_status = "PARTIALLY_SETTLED"
        else:
            settlement_status = "UNSETTLED"

        payment_request_responses = []
        for r in agreement.payment_requests:
            if not r.captures:
                stmt_c = (
                    select(PaymentCapture)
                    .where(PaymentCapture.payment_request_id == r.id)
                    .order_by(PaymentCapture.created_at.desc())
                )
                r.captures = list((await db.execute(stmt_c)).scalars().all())
            payment_request_responses.append(cls._build_payment_request_response(r, current_user, agreement))

        return AgreementSettlementSummaryResponse(
            agreement_id=agreement.id,
            agreement_title=agreement.title,
            agreement_version=agreement.version,
            agreement_status=agreement.status,
            consensus_achieved=is_consensus,
            total_obligations_amount=total_obligations,
            currency=currency,
            total_completed_amount=total_completed,
            total_pending_amount=total_pending,
            total_failed_amount=total_failed,
            outstanding_balance=outstanding,
            settlement_status=settlement_status,
            obligations=obligation_summaries,
            payment_requests=payment_request_responses,
        )

    @classmethod
    def _build_payment_request_response(
        cls,
        req: PaymentRequest,
        current_user: User,
        agreement: Optional[Agreement] = None,
    ) -> PaymentRequestResponse:
        """Helper to build rich PaymentRequestResponse with permission flags."""
        settings = get_settings()
        client_id = settings.PAYPAL_CLIENT_ID

        debtor_user_id = None
        agr = agreement or req.agreement
        if agr and hasattr(agr, "participants"):
            for p in agr.participants:
                if p.id == req.debtor_participant_id:
                    debtor_user_id = p.user_id
                    break

        is_owner = (agr.owner_id == current_user.id) if agr else False
        is_debtor = (debtor_user_id == current_user.id) if debtor_user_id else False

        can_pay = req.status in ("DRAFT", "PENDING", "APPROVED") and (is_debtor or is_owner)
        can_cancel = req.status in ("DRAFT", "PENDING") and (is_owner or req.created_by_user_id == current_user.id)
        can_refund = req.status == "COMPLETED" and is_owner

        is_mock_mode = get_paypal_client().mock_mode

        from app.payments.currency_service import CurrencyService, FALLBACK_USD_RATES

        active_order_resp = None
        is_converted = False
        paypal_amount = None
        paypal_currency = None
        exchange_rate = None

        if req.orders:
            latest_ord = req.orders[0]
            if latest_ord.currency != req.currency:
                is_converted = True
                paypal_amount = latest_ord.amount
                paypal_currency = latest_ord.currency
                if latest_ord.amount > Decimal("0.00"):
                    exchange_rate = (Decimal(str(req.amount)) / Decimal(str(latest_ord.amount))).quantize(Decimal("0.0001"))
            else:
                paypal_amount = latest_ord.amount
                paypal_currency = latest_ord.currency
                exchange_rate = Decimal("1.0000")

            active_order_resp = PayPalOrderResponse(
                id=latest_ord.id,
                payment_request_id=latest_ord.payment_request_id,
                paypal_order_id=latest_ord.paypal_order_id,
                amount=latest_ord.amount,
                currency=latest_ord.currency,
                status=latest_ord.status,
                approval_url=latest_ord.approval_url,
                client_id=client_id,
                is_mock=is_mock_mode,
                original_amount=req.amount,
                original_currency=req.currency,
                exchange_rate=exchange_rate,
                is_converted=is_converted,
            )
        elif not CurrencyService.is_paypal_supported(req.currency):
            rates = CurrencyService._cached_rates or FALLBACK_USD_RATES
            rate = rates.get(req.currency.upper(), FALLBACK_USD_RATES.get(req.currency.upper(), Decimal("93.85")))
            if rate > Decimal("0.00"):
                paypal_amount = (Decimal(str(req.amount)) / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                paypal_currency = "USD"
                exchange_rate = rate.quantize(Decimal("0.0001"))
                is_converted = True
        else:
            paypal_amount = req.amount
            paypal_currency = req.currency
            exchange_rate = Decimal("1.0000")
            is_converted = False

        latest_capture_resp = None
        if req.captures:
            latest_cap = req.captures[0]
            latest_capture_resp = PaymentCaptureResponse(
                id=latest_cap.id,
                payment_request_id=latest_cap.payment_request_id,
                paypal_order_id=latest_cap.paypal_order_id,
                paypal_capture_id=latest_cap.paypal_capture_id,
                amount=latest_cap.amount,
                currency=latest_cap.currency,
                status=latest_cap.status,
                paypal_fee=latest_cap.paypal_fee,
                net_amount=latest_cap.net_amount,
                captured_at=latest_cap.captured_at,
            )

        return PaymentRequestResponse(
            id=req.id,
            agreement_id=req.agreement_id,
            agreement_version=req.agreement_version,
            obligation_id=req.obligation_id,
            debtor_participant_id=req.debtor_participant_id,
            creditor_participant_id=req.creditor_participant_id,
            debtor_name=req.debtor_name,
            creditor_name=req.creditor_name,
            receiver_merchant_account=req.receiver_merchant_account,
            amount=req.amount,
            currency=req.currency,
            status=req.status,
            due_date=req.due_date,
            paypal_order_id=req.paypal_order_id,
            created_by_user_id=req.created_by_user_id,
            created_at=req.created_at,
            updated_at=req.updated_at,
            can_pay=can_pay,
            can_cancel=can_cancel,
            can_refund=can_refund,
            is_mock=is_mock_mode,
            active_order=active_order_resp,
            latest_capture=latest_capture_resp,
            paypal_amount=paypal_amount,
            paypal_currency=paypal_currency,
            exchange_rate=exchange_rate,
            is_converted=is_converted,
        )
