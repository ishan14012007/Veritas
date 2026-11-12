import hashlib
import hmac
import logging
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.accord.models.agreement import Agreement, AgreementHistory, AgreementParticipant
from app.accord.models.ambiguity import Ambiguity
from app.accord.models.conversation import Conversation
from app.accord.models.message import Message
from app.accord.models.participant import Participant
from app.accord.services.analyzer import ConversationAnalyzerService
from app.core.config import get_settings
from app.core.models.user import User
from app.payments.models import PaymentCapture, PaymentRefund, PaymentRequest
from app.whatsapp.client import get_whatsapp_provider
from app.whatsapp.models import (
    WhatsAppAccount,
    WhatsAppMessage,
    WhatsAppMessageTemplate,
    WhatsAppWebhookEvent,
)

logger = logging.getLogger(__name__)


class WhatsAppService:
    """Orchestrates WhatsApp Business messaging, user account linking, inbound message ingestion,
    ACCORD conversation routing, Gemini analysis integration, and pre-approved template notifications.
    """

    # --------------------------------------------------------------------------
    # 1. Phone Number Linking and Identity Binding
    # --------------------------------------------------------------------------

    @classmethod
    def normalize_phone_number(cls, phone: str) -> str:
        """Normalize phone number to standard E.164 format (+14155552671)."""
        clean = phone.strip().replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        if not clean.startswith("+"):
            clean = f"+{clean}"
        if len(clean) < 8 or len(clean) > 20:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid phone number format. Must be a valid E.164 phone number.",
            )
        return clean

    @classmethod
    async def link_phone_number(
        cls,
        db: AsyncSession,
        user: User,
        phone_number: str,
        display_name: Optional[str] = None,
    ) -> WhatsAppAccount:
        """Initiate phone number linking. Generates a short-lived cryptographic single-use verification token."""
        normalized_phone = cls.normalize_phone_number(phone_number)
        settings = get_settings()

        # Check if phone number is already verified and bound to ANOTHER user
        stmt_existing = select(WhatsAppAccount).where(
            WhatsAppAccount.phone_number == normalized_phone,
            WhatsAppAccount.connection_status == "CONNECTED",
            WhatsAppAccount.user_id != user.id,
        )
        existing = (await db.execute(stmt_existing)).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This phone number is already linked and verified by another VERITAS user.",
            )

        # Generate a 6-digit cryptographically random verification code
        token_code = "".join(secrets.choice("0123456789") for _ in range(6))
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

        # Check if account already exists for this user and number
        stmt_user_acc = select(WhatsAppAccount).where(
            WhatsAppAccount.phone_number == normalized_phone,
            WhatsAppAccount.user_id == user.id,
        )
        account = (await db.execute(stmt_user_acc)).scalar_one_or_none()

        if account:
            account.verification_token = token_code
            account.verification_token_expires_at = expires_at
            account.connection_status = "PENDING_VERIFICATION"
            if display_name:
                account.display_name = display_name
        else:
            account = WhatsAppAccount(
                id=uuid.uuid4(),
                user_id=user.id,
                phone_number=normalized_phone,
                display_name=display_name or user.full_name,
                provider=settings.WHATSAPP_PROVIDER,
                phone_number_id=settings.WHATSAPP_PHONE_NUMBER_ID,
                business_account_id=settings.WHATSAPP_BUSINESS_ACCOUNT_ID,
                connection_status="PENDING_VERIFICATION",
                consent_status="OPTED_OUT",
                verification_token=token_code,
                verification_token_expires_at=expires_at,
            )
            db.add(account)

        await db.commit()
        await db.refresh(account)

        logger.info(
            f"[WHATSAPP_LINKING] Generated linking token for {normalized_phone} (User: {user.email}). "
            f"MockMode={settings.is_whatsapp_mock}"
        )

        return account

    @classmethod
    async def verify_phone_number(
        cls,
        db: AsyncSession,
        user: User,
        phone_number: str,
        verification_token: str,
    ) -> WhatsAppAccount:
        """Verify control of the phone number using the single-use token."""
        normalized_phone = cls.normalize_phone_number(phone_number)
        now = datetime.now(timezone.utc)

        stmt = select(WhatsAppAccount).where(
            WhatsAppAccount.phone_number == normalized_phone,
            WhatsAppAccount.user_id == user.id,
        )
        account = (await db.execute(stmt)).scalar_one_or_none()

        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No pending linking request found for this phone number.",
            )

        if account.connection_status == "CONNECTED":
            return account

        if not account.verification_token or not account.verification_token_expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active verification token found. Please request a new linking code.",
            )

        expires_at = account.verification_token_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if now > expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code has expired. Please initiate linking again.",
            )

        if not hmac.compare_digest(account.verification_token, verification_token.strip()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code. Please check and try again.",
            )

        # Mark account verified & opted in
        account.connection_status = "CONNECTED"
        account.consent_status = "OPTED_IN"
        account.verified_at = now
        account.verification_token = None
        account.verification_token_expires_at = None

        # Update core user model phone & opt-in
        user.phone_number = normalized_phone
        user.whatsapp_opt_in = True
        user.whatsapp_opt_in_at = now
        db.add(user)

        await db.commit()
        await db.refresh(account)

        logger.info(f"[WHATSAPP_LINKING] Successfully verified phone {normalized_phone} for user {user.email}.")
        return account

    @classmethod
    async def get_user_accounts(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> List[WhatsAppAccount]:
        """Fetch all WhatsApp accounts linked to the user."""
        stmt = (
            select(WhatsAppAccount)
            .where(WhatsAppAccount.user_id == user_id)
            .order_by(WhatsAppAccount.created_at.desc())
        )
        return list((await db.execute(stmt)).scalars().all())

    @classmethod
    async def unlink_account(
        cls,
        db: AsyncSession,
        user: User,
        account_id: uuid.UUID,
    ) -> bool:
        """Unlink a WhatsApp number from the authenticated user."""
        stmt = select(WhatsAppAccount).where(
            WhatsAppAccount.id == account_id,
            WhatsAppAccount.user_id == user.id,
        )
        account = (await db.execute(stmt)).scalar_one_or_none()
        if not account:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="WhatsApp account not found or access denied.",
            )

        account.connection_status = "DISCONNECTED"
        account.consent_status = "OPTED_OUT"

        # If user's primary phone matches, clear opt-in
        if user.phone_number == account.phone_number:
            user.whatsapp_opt_in = False

        db.add(user)
        await db.commit()
        logger.info(f"[WHATSAPP_LINKING] Account {account_id} ({account.phone_number}) unlinked by {user.email}.")
        return True

    # --------------------------------------------------------------------------
    # 2. Outbound Message Dispatching
    # --------------------------------------------------------------------------

    @classmethod
    async def send_message(
        cls,
        db: AsyncSession,
        recipient_number: str,
        content: str,
        message_type: str = "TEXT",
        template_name: Optional[str] = None,
        template_parameters: Optional[List[Dict[str, Any]]] = None,
        conversation_id: Optional[uuid.UUID] = None,
        user: Optional[User] = None,
    ) -> WhatsAppMessage:
        """Send an outbound text or template message via the configured WhatsApp provider."""
        normalized_recipient = cls.normalize_phone_number(recipient_number)
        provider = get_whatsapp_provider()
        settings = get_settings()

        # Check opt-in consent if sending business template
        if message_type.upper() == "TEMPLATE" and user is not None and not user.whatsapp_opt_in:
            logger.warning(f"[WHATSAPP_OUTBOUND] User {user.email} has opted out of WhatsApp messages. Skipping.")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recipient user has opted out of WhatsApp notifications.",
            )

        # Dispatch via provider
        if message_type.upper() == "TEMPLATE" and template_name:
            res = await provider.send_template_message(
                to=normalized_recipient,
                template_name=template_name,
                components=template_parameters,
            )
            msg_content = f"[Template: {template_name}] {content or ''}".strip()
        else:
            res = await provider.send_text_message(
                to=normalized_recipient,
                text=content,
            )
            msg_content = content

        # Extract provider message ID
        provider_msg_id = ""
        if "messages" in res and res["messages"]:
            provider_msg_id = res["messages"][0].get("id", "")
        if not provider_msg_id:
            provider_msg_id = f"wamid.{uuid.uuid4().hex[:16]}"

        # Find linked account for sender/recipient
        stmt_acc = select(WhatsAppAccount).where(WhatsAppAccount.phone_number == normalized_recipient)
        linked_acc = (await db.execute(stmt_acc)).scalar_one_or_none()

        sender_num = settings.WHATSAPP_PHONE_NUMBER_ID or "15550001234"
        if not sender_num.startswith("+"):
            sender_num = f"+{sender_num}"

        message_record = WhatsAppMessage(
            id=uuid.uuid4(),
            user_id=user.id if user else None,
            account_id=linked_acc.id if linked_acc else None,
            conversation_id=conversation_id,
            provider_message_id=provider_msg_id,
            sender_number=sender_num,
            recipient_number=normalized_recipient,
            direction="OUTBOUND",
            message_type=message_type.upper(),
            content=msg_content,
            raw_payload=res,
            provider=provider.provider_name,
            delivery_status="SENT",
            is_mock=provider.is_mock,
        )
        db.add(message_record)
        await db.commit()
        await db.refresh(message_record)

        return message_record

    # --------------------------------------------------------------------------
    # 3. Inbound Webhook Processing & ACCORD Integration
    # --------------------------------------------------------------------------

    @classmethod
    async def process_webhook_event(
        cls,
        db: AsyncSession,
        event_id: uuid.UUID,
        trigger_analysis: bool = False,
    ) -> List[WhatsAppMessage]:
        """Process a received WhatsApp webhook event:
        1. Parse normalized inbound messages and status updates.
        2. Resolve linked user from sender phone number.
        3. Persist messages and route to ACCORD conversation.
        4. Optionally run Gemini intelligence extraction.
        """
        event = await db.get(WhatsAppWebhookEvent, event_id)
        if not event:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook event not found.")

        if event.processing_status == "PROCESSED":
            return []

        provider = get_whatsapp_provider()
        payload = event.payload
        processed_messages: List[WhatsAppMessage] = []

        try:
            # A. Process delivery status updates (sent, delivered, read, failed)
            status_updates = provider.process_status_update(payload)
            for s in status_updates:
                p_id = s.get("provider_message_id")
                new_status = s.get("status", "").upper()
                if p_id:
                    stmt_msg = select(WhatsAppMessage).where(WhatsAppMessage.provider_message_id == p_id)
                    existing_msg = (await db.execute(stmt_msg)).scalar_one_or_none()
                    if existing_msg:
                        existing_msg.delivery_status = new_status
                        if s.get("error_code"):
                            existing_msg.error_code = s["error_code"]
                            existing_msg.error_message = s.get("error_message")
                        db.add(existing_msg)

            # B. Process incoming customer/user messages
            inbound_items = provider.process_inbound_message(payload)
            for item in inbound_items:
                sender_num = item["sender_number"]
                raw_text = item["content"]
                p_msg_id = item["provider_message_id"]

                # 1. Check if sender phone is linked to a verified VERITAS account
                stmt_acc = select(WhatsAppAccount).where(
                    WhatsAppAccount.phone_number == sender_num,
                    WhatsAppAccount.connection_status == "CONNECTED",
                )
                account = (await db.execute(stmt_acc)).scalar_one_or_none()

                if not account:
                    logger.warning(
                        f"[WHATSAPP_INBOUND] Received message from unverified/unlinked number {sender_num}. "
                        "Rejecting conversation creation per security policy."
                    )
                    # Persist record for security audit with status UNAUTHORIZED_SENDER
                    unauth_record = WhatsAppMessage(
                        id=uuid.uuid4(),
                        provider_message_id=p_msg_id,
                        sender_number=sender_num,
                        recipient_number=item.get("recipient_number", "unknown"),
                        direction="INBOUND",
                        message_type=item.get("message_type", "TEXT"),
                        content=raw_text,
                        raw_payload=item.get("raw"),
                        provider=provider.provider_name,
                        delivery_status="FAILED",
                        error_code="UNAUTHORIZED_SENDER",
                        error_message="Phone number not linked to any active VERITAS account.",
                        is_mock=provider.is_mock,
                    )
                    db.add(unauth_record)
                    processed_messages.append(unauth_record)
                    continue

                # 2. Authorized user: Find or create ACCORD conversation
                user_id = account.user_id

                # Find the user's latest WhatsApp conversation or create a new one
                stmt_conv = (
                    select(Conversation)
                    .where(
                        Conversation.owner_id == user_id,
                        Conversation.source_type == "WHATSAPP_DIRECT",
                        Conversation.deleted_at.is_(None),
                    )
                    .order_by(Conversation.created_at.desc())
                )
                conv = (await db.execute(stmt_conv)).scalars().first()

                if not conv:
                    conv = Conversation(
                        id=uuid.uuid4(),
                        owner_id=user_id,
                        title=f"WhatsApp Inbound Chat ({sender_num})",
                        source_type="WHATSAPP_DIRECT",
                        raw_transcript=raw_text,
                        processing_status="COMPLETED",
                    )
                    db.add(conv)
                    await db.flush()
                else:
                    # Append text to raw_transcript
                    conv.raw_transcript += f"\n[{datetime.now(timezone.utc).strftime('%m/%d/%y, %H:%M')}] {account.display_name or sender_num}: {raw_text}"
                    db.add(conv)

                # Ensure participant record for sender
                stmt_part = select(Participant).where(
                    Participant.conversation_id == conv.id,
                    Participant.sender_identifier == sender_num,
                )
                conv_part = (await db.execute(stmt_part)).scalar_one_or_none()
                if not conv_part:
                    conv_part = Participant(
                        id=uuid.uuid4(),
                        conversation_id=conv.id,
                        display_name=account.display_name or sender_num,
                        sender_identifier=sender_num,
                    )
                    db.add(conv_part)
                    await db.flush()

                # 3. Add message to accord.messages
                # Get max order index for this conversation
                stmt_idx = select(func.coalesce(func.max(Message.order_index), 0)).where(Message.conversation_id == conv.id)
                curr_max = (await db.execute(stmt_idx)).scalar_one() or 0

                msg_order = curr_max + 1
                accord_msg = Message(
                    id=uuid.uuid4(),
                    conversation_id=conv.id,
                    participant_id=conv_part.id,
                    sender_name=account.display_name or sender_num,
                    message_body=raw_text,
                    original_timestamp=datetime.now(timezone.utc),
                    order_index=msg_order,
                    is_system_message=False,
                )
                db.add(accord_msg)
                await db.flush()

                # 4. Record WhatsAppMessage
                wa_msg = WhatsAppMessage(
                    id=uuid.uuid4(),
                    user_id=user_id,
                    account_id=account.id,
                    conversation_id=conv.id,
                    accord_message_id=accord_msg.id,
                    provider_message_id=p_msg_id,
                    sender_number=sender_num,
                    recipient_number=item.get("recipient_number", "15550001234"),
                    direction="INBOUND",
                    message_type=item.get("message_type", "TEXT"),
                    content=raw_text,
                    raw_payload=item.get("raw"),
                    provider=provider.provider_name,
                    delivery_status="DELIVERED",
                    is_mock=provider.is_mock,
                )
                db.add(wa_msg)
                processed_messages.append(wa_msg)

                # 5. Trigger Gemini conversation intelligence if requested
                if trigger_analysis:
                    try:
                        logger.info(f"[WHATSAPP_AI] Triggering Gemini analysis for conversation {conv.id}...")
                        await ConversationAnalyzerService.execute_analysis(
                            db=db,
                            conversation_id=conv.id,
                            user_id=user_id,
                        )
                    except Exception as ai_err:
                        logger.warning(f"[WHATSAPP_AI] Analysis trigger failed: {ai_err}")

            event.processing_status = "PROCESSED"
            event.processed_at = datetime.now(timezone.utc)
            db.add(event)
            await db.commit()

            return processed_messages

        except Exception as exc:
            await db.rollback()
            event.processing_status = "FAILED"
            event.error_detail = str(exc)
            db.add(event)
            await db.commit()
            logger.error(f"[WHATSAPP_WEBHOOK] Failed processing event {event_id}: {exc}")
            raise

    # --------------------------------------------------------------------------
    # 4. Outbound ACCORD Notifications
    # --------------------------------------------------------------------------

    @classmethod
    async def notify_agreement_ready_for_review(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        portal_base_url: str = "http://localhost:5173",
    ) -> List[WhatsAppMessage]:
        """Notify all participants that agreement is ready for review and individual consent."""
        agreement = await db.get(
            Agreement,
            agreement_id,
            options=[
                selectinload(Agreement.participants).selectinload(AgreementParticipant.user),
            ],
        )
        if not agreement:
            return []

        sent_messages: List[WhatsAppMessage] = []
        review_url = f"{portal_base_url}/accord"

        for p in agreement.participants:
            user = p.user
            if not user or not user.phone_number or not user.whatsapp_opt_in:
                continue

            text = (
                f"Hello {p.name}! Agreement v{agreement.version} ('{agreement.title}') is ready for your review on VERITAS ACCORD.\n\n"
                f"Total value: ${agreement.total_value:.2f} {agreement.currency}\n"
                f"Review & submit your consent: {review_url}"
            )

            try:
                msg = await cls.send_message(
                    db=db,
                    recipient_number=user.phone_number,
                    content=text,
                    message_type="TEXT",
                    conversation_id=agreement.conversation_id,
                    user=user,
                )
                sent_messages.append(msg)
            except Exception as e:
                logger.warning(f"Could not send review notification to {user.phone_number}: {e}")

        return sent_messages

    @classmethod
    async def notify_agreement_confirmed(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        portal_base_url: str = "http://localhost:5173",
    ) -> List[WhatsAppMessage]:
        """Notify participants that full mutual consensus was reached."""
        agreement = await db.get(
            Agreement,
            agreement_id,
            options=[
                selectinload(Agreement.participants).selectinload(AgreementParticipant.user),
            ],
        )
        if not agreement:
            return []

        sent_messages: List[WhatsAppMessage] = []
        for p in agreement.participants:
            user = p.user
            if not user or not user.phone_number or not user.whatsapp_opt_in:
                continue

            text = (
                f"Consensus Achieved! All participants have accepted Agreement v{agreement.version} "
                f"('{agreement.title}') on VERITAS ACCORD.\n\n"
                f"Obligations are now unlocked for settlement: {portal_base_url}/accord"
            )
            try:
                msg = await cls.send_message(
                    db=db,
                    recipient_number=user.phone_number,
                    content=text,
                    message_type="TEXT",
                    conversation_id=agreement.conversation_id,
                    user=user,
                )
                sent_messages.append(msg)
            except Exception as e:
                logger.warning(f"Could not send consensus notification to {user.phone_number}: {e}")

        return sent_messages

    @classmethod
    async def notify_payment_request_created(
        cls,
        db: AsyncSession,
        payment_request_id: uuid.UUID,
        portal_base_url: str = "http://localhost:5173",
    ) -> Optional[WhatsAppMessage]:
        """Notify debtor that a payment request has been issued with secure VERITAS portal link."""
        stmt = (
            select(PaymentRequest)
            .where(PaymentRequest.id == payment_request_id)
            .options(
                selectinload(PaymentRequest.agreement).selectinload(Agreement.participants).selectinload(AgreementParticipant.user)
            )
        )
        req = (await db.execute(stmt)).scalar_one_or_none()
        if not req:
            return None

        # Find debtor user account
        debtor_part = next((p for p in req.agreement.participants if p.name == req.debtor_name), None)
        user = debtor_part.user if debtor_part else None

        if not user or not user.phone_number or not user.whatsapp_opt_in:
            return None

        # Secure checkout portal URL (NO sensitive PayPal secrets in WhatsApp!)
        checkout_url = f"{portal_base_url}/accord"
        text = (
            f"VERITAS ACCORD: Payment Request for ${req.amount:.2f} {req.currency}\n\n"
            f"Payee: {req.creditor_name}\n"
            f"Agreement: {req.agreement.title}\n"
            f"Complete checkout securely via PayPal: {checkout_url}"
        )

        return await cls.send_message(
            db=db,
            recipient_number=user.phone_number,
            content=text,
            message_type="TEXT",
            conversation_id=req.agreement.conversation_id,
            user=user,
        )

    @classmethod
    async def notify_payment_captured(
        cls,
        db: AsyncSession,
        capture_id: uuid.UUID,
        portal_base_url: str = "http://localhost:5173",
    ) -> List[WhatsAppMessage]:
        """Notify debtor and creditor that PayPal capture was successful."""
        stmt = (
            select(PaymentCapture)
            .where(PaymentCapture.id == capture_id)
            .options(
                selectinload(PaymentCapture.payment_request).selectinload(PaymentRequest.agreement).selectinload(Agreement.participants).selectinload(AgreementParticipant.user)
            )
        )
        cap = (await db.execute(stmt)).scalar_one_or_none()
        if not cap or not cap.payment_request:
            return []

        req = cap.payment_request
        agreement = req.agreement
        sent_messages: List[WhatsAppMessage] = []

        for p in agreement.participants:
            user = p.user
            if not user or not user.phone_number or not user.whatsapp_opt_in:
                continue

            if p.name == req.debtor_name:
                text = (
                    f"Payment Confirmed! Your payment of ${cap.amount:.2f} {cap.currency} to {req.creditor_name} "
                    f"has been captured via PayPal (Capture ID: {cap.paypal_capture_id}). View status: {portal_base_url}/accord"
                )
            elif p.name == req.creditor_name:
                text = (
                    f"Payment Received! {req.debtor_name} settled ${cap.amount:.2f} {cap.currency} via PayPal "
                    f"(Capture ID: {cap.paypal_capture_id}) for Agreement '{agreement.title}'. View status: {portal_base_url}/accord"
                )
            else:
                continue

            try:
                msg = await cls.send_message(
                    db=db,
                    recipient_number=user.phone_number,
                    content=text,
                    message_type="TEXT",
                    conversation_id=agreement.conversation_id,
                    user=user,
                )
                sent_messages.append(msg)
            except Exception as e:
                logger.warning(f"Could not send capture notification to {user.phone_number}: {e}")

        return sent_messages

    @classmethod
    async def notify_settlement_completed(
        cls,
        db: AsyncSession,
        agreement_id: uuid.UUID,
        portal_base_url: str = "http://localhost:5173",
    ) -> List[WhatsAppMessage]:
        """Notify all participants that agreement obligations are FULLY_SETTLED."""
        agreement = await db.get(
            Agreement,
            agreement_id,
            options=[
                selectinload(Agreement.participants).selectinload(AgreementParticipant.user),
            ],
        )
        if not agreement:
            return []

        sent_messages: List[WhatsAppMessage] = []
        for p in agreement.participants:
            user = p.user
            if not user or not user.phone_number or not user.whatsapp_opt_in:
                continue

            text = (
                f"Agreement FULLY SETTLED! All obligations for Agreement '{agreement.title}' have been fulfilled. "
                f"Thank you for using VERITAS ACCORD: {portal_base_url}/accord"
            )
            try:
                msg = await cls.send_message(
                    db=db,
                    recipient_number=user.phone_number,
                    content=text,
                    message_type="TEXT",
                    conversation_id=agreement.conversation_id,
                    user=user,
                )
                sent_messages.append(msg)
            except Exception as e:
                logger.warning(f"Could not send full settlement notification to {user.phone_number}: {e}")

        return sent_messages

    # --------------------------------------------------------------------------
    # 5. Queries & Status
    # --------------------------------------------------------------------------

    @classmethod
    async def get_messages(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        conversation_id: Optional[uuid.UUID] = None,
        direction: Optional[str] = None,
        delivery_status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> List[WhatsAppMessage]:
        """Query WhatsApp messages belonging to user's linked accounts or conversations."""
        # Find all phone numbers linked to this user
        user_phones = (
            await db.execute(
                select(WhatsAppAccount.phone_number).where(WhatsAppAccount.user_id == user_id)
            )
        ).scalars().all()

        query = select(WhatsAppMessage).order_by(desc(WhatsAppMessage.created_at))

        # Filter by participant phone, user_id, or owned conversations
        if conversation_id:
            query = query.where(WhatsAppMessage.conversation_id == conversation_id)
        else:
            filter_conditions = [WhatsAppMessage.user_id == user_id]
            if user_phones:
                filter_conditions.append(WhatsAppMessage.sender_number.in_(user_phones))
                filter_conditions.append(WhatsAppMessage.recipient_number.in_(user_phones))
            query = query.where(or_(*filter_conditions))

        if direction:
            query = query.where(WhatsAppMessage.direction == direction.upper())
        if delivery_status:
            query = query.where(WhatsAppMessage.delivery_status == delivery_status.upper())

        query = query.offset((page - 1) * page_size).limit(page_size)
        return list((await db.execute(query)).scalars().all())

    @classmethod
    async def get_message_by_id(
        cls,
        db: AsyncSession,
        user_id: uuid.UUID,
        message_id: uuid.UUID,
    ) -> WhatsAppMessage:
        """Fetch WhatsApp message with authorization check."""
        msg = await db.get(WhatsAppMessage, message_id)
        if not msg:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

        # Authorization: user must own linked account, be sender, or own conversation
        user_phones = (
            await db.execute(
                select(WhatsAppAccount.phone_number).where(WhatsAppAccount.user_id == user_id)
            )
        ).scalars().all()

        is_owner = (
            msg.user_id == user_id
            or msg.sender_number in user_phones
            or msg.recipient_number in user_phones
        )
        if not is_owner and msg.conversation_id:
            conv = await db.get(Conversation, msg.conversation_id)
            if conv and conv.owner_id == user_id:
                is_owner = True

        if not is_owner:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found.")

        return msg

    @classmethod
    async def get_status(cls, db: AsyncSession) -> Dict[str, Any]:
        """Get high-level status of WhatsApp integration."""
        provider = get_whatsapp_provider()
        settings = get_settings()

        accounts_count = (await db.execute(select(func.count(WhatsAppAccount.id)))).scalar_one() or 0
        messages_count = (await db.execute(select(func.count(WhatsAppMessage.id)))).scalar_one() or 0

        templates = (
            await db.execute(
                select(WhatsAppMessageTemplate.template_name).where(WhatsAppMessageTemplate.approval_status == "APPROVED")
            )
        ).scalars().all()

        return {
            "provider": provider.provider_name,
            "mock_mode": provider.is_mock,
            "phone_number_id": getattr(provider, "phone_number_id", "mock_phone_id"),
            "webhook_url": f"{settings.API_V1_STR}/whatsapp/webhook",
            "linked_accounts_count": accounts_count,
            "total_messages_count": messages_count,
            "registered_templates": list(templates) or [
                "accord_agreement_review_v1",
                "accord_consensus_confirmed_v1",
                "accord_payment_request_v1",
                "accord_payment_received_v1",
                "accord_settlement_completed_v1",
            ],
        }
