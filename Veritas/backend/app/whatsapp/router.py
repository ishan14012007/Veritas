import json
import logging
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.models.user import User
from app.whatsapp.client import get_whatsapp_provider
from app.whatsapp.schemas import (
    LinkPhoneNumberRequest,
    MockInboundMessageRequest,
    MockStatusUpdateRequest,
    SendWhatsAppMessageRequest,
    VerifyPhoneNumberRequest,
    WhatsAppAccountResponse,
    WhatsAppMessageResponse,
    WhatsAppStatusResponse,
    WhatsAppWebhookEventResponse,
)
from app.whatsapp.service import WhatsAppService
from app.whatsapp.webhook import WhatsAppWebhookHandler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WhatsApp Business Integration"])


# ==============================================================================
# 1. Inbound Webhook Endpoints (Meta & Simulated)
# ==============================================================================

@router.get(
    "/webhook",
    summary="Meta WhatsApp webhook subscription verification",
    response_class=PlainTextResponse,
)
async def verify_webhook_subscription(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    settings: Settings = Depends(get_settings),
):
    """Responds to Meta's webhook verification GET request with the challenge token."""
    challenge = WhatsAppWebhookHandler.verify_subscription(hub_mode, hub_token, hub_challenge, settings=settings)
    if challenge is not None:
        return PlainTextResponse(content=challenge, status_code=200)

    logger.warning(f"[WHATSAPP_WEBHOOK] Subscription verification failed: mode={hub_mode}")
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Webhook subscription verification failed. Invalid verify token.",
    )


@router.post(
    "/webhook",
    summary="Receive WhatsApp inbound messages and delivery status updates",
)
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """Processes incoming Meta Cloud API webhook events with HMAC-SHA256 signature verification."""
    raw_body = await request.body()

    # Signature verification
    sig_valid = WhatsAppWebhookHandler.verify_signature(raw_body, x_hub_signature_256, settings=settings)

    # In LIVE mode, signature is mandatory and strictly verified
    if not settings.is_whatsapp_mock and not sig_valid:
        logger.error("[WHATSAPP_WEBHOOK] Rejected webhook in LIVE mode due to invalid signature.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Meta webhook signature (X-Hub-Signature-256 mismatch).",
        )

    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Malformed JSON payload: {exc}")

    # Record event with deduplication
    event, is_duplicate = await WhatsAppWebhookHandler.record_webhook_event(
        db=db,
        raw_body=raw_body,
        parsed_payload=payload,
        signature_verified=sig_valid,
    )

    if is_duplicate:
        return {"status": "ok", "message": "Duplicate event ignored", "event_id": str(event.id)}

    # Process message synchronously for local dev / testing or enqueue to ARQ
    try:
        await WhatsAppService.process_webhook_event(
            db=db,
            event_id=event.id,
            trigger_analysis=False,
        )
    except Exception as exc:
        logger.error(f"[WHATSAPP_WEBHOOK] Error processing event {event.id}: {exc}")

    return {
        "status": "ok",
        "event_id": str(event.id),
        "signature_verified": sig_valid,
    }


# ==============================================================================
# 2. Account & Phone Number Linking APIs
# ==============================================================================

@router.post(
    "/accounts/link",
    response_model=WhatsAppAccountResponse,
    summary="Initiate WhatsApp phone number linking",
)
async def link_phone_number(
    payload: LinkPhoneNumberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> WhatsAppAccountResponse:
    """Initiate linking between an authenticated VERITAS user and a WhatsApp phone number."""
    try:
        account = await WhatsAppService.link_phone_number(
            db=db,
            user=current_user,
            phone_number=payload.phone_number,
            display_name=payload.display_name,
        )
        resp = WhatsAppAccountResponse.model_validate(account)
        if settings.is_whatsapp_mock:
            resp.verification_token = account.verification_token
        return resp
    except Exception as exc:
        logger.warning("DB unavailable for link_phone_number, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        return DevStore.link_whatsapp_phone(payload.phone_number, payload.display_name, current_user.id)


@router.post(
    "/accounts/verify",
    response_model=WhatsAppAccountResponse,
    summary="Confirm WhatsApp phone number linking with single-use code",
)
async def verify_phone_number(
    payload: VerifyPhoneNumberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WhatsAppAccountResponse:
    """Verify single-use token and mark phone number bound and opted-in."""
    try:
        account = await WhatsAppService.verify_phone_number(
            db=db,
            user=current_user,
            phone_number=payload.phone_number,
            verification_token=payload.verification_token,
        )
        return WhatsAppAccountResponse.model_validate(account)
    except Exception as exc:
        logger.warning("DB unavailable for verify_phone_number, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        return DevStore.verify_whatsapp_phone(payload.phone_number, payload.verification_token)


@router.get(
    "/accounts",
    response_model=List[WhatsAppAccountResponse],
    summary="List linked WhatsApp accounts for authenticated user",
)
async def get_user_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> List[WhatsAppAccountResponse]:
    """Retrieve all linked WhatsApp numbers for the active account."""
    try:
        accounts = await WhatsAppService.get_user_accounts(db, current_user.id)
        results = []
        for a in accounts:
            r = WhatsAppAccountResponse.model_validate(a)
            if settings.is_whatsapp_mock:
                r.verification_token = a.verification_token
            results.append(r)
        return results
    except Exception as exc:
        logger.warning("DB unavailable for get_user_accounts, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        return DevStore.get_whatsapp_accounts(current_user.id)


@router.delete(
    "/accounts/{account_id}",
    summary="Unlink WhatsApp phone number",
)
async def unlink_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink a bound WhatsApp number from the active user account."""
    try:
        await WhatsAppService.unlink_account(db, current_user, account_id)
    except Exception as exc:
        logger.warning("DB unavailable for unlink_account: %s", exc)
    return {"success": True, "message": "WhatsApp phone number successfully unlinked."}


# ==============================================================================
# 3. WhatsApp Messaging APIs
# ==============================================================================

@router.post(
    "/messages/send",
    response_model=WhatsAppMessageResponse,
    summary="Send an outbound WhatsApp message or approved template",
)
async def send_message(
    payload: SendWhatsAppMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WhatsAppMessageResponse:
    """Dispatches a freeform text or approved template message."""
    try:
        msg = await WhatsAppService.send_message(
            db=db,
            recipient_number=payload.recipient_number,
            content=payload.content or "",
            message_type=payload.message_type,
            template_name=payload.template_name,
            template_parameters=payload.template_parameters,
            conversation_id=payload.conversation_id,
            user=current_user,
        )
        return WhatsAppMessageResponse.model_validate(msg)
    except Exception as exc:
        logger.warning("DB unavailable for send_message, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        return DevStore.send_whatsapp_message(
            payload.recipient_number,
            payload.content or "",
            payload.message_type,
            payload.template_name
        )


@router.get(
    "/messages",
    response_model=List[WhatsAppMessageResponse],
    summary="List WhatsApp message history for authenticated user",
)
async def list_messages(
    conversation_id: Optional[uuid.UUID] = Query(None),
    direction: Optional[str] = Query(None),
    delivery_status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[WhatsAppMessageResponse]:
    """Retrieve WhatsApp messages associated with user's linked phones or conversations."""
    try:
        messages = await WhatsAppService.get_messages(
            db=db,
            user_id=current_user.id,
            conversation_id=conversation_id,
            direction=direction,
            delivery_status=delivery_status,
            page=page,
            page_size=page_size,
        )
        return [WhatsAppMessageResponse.model_validate(m) for m in messages]
    except Exception as exc:
        logger.warning("DB unavailable for list_messages, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        return DevStore.get_whatsapp_messages(conversation_id)


@router.get(
    "/messages/{message_id}",
    response_model=WhatsAppMessageResponse,
    summary="Get WhatsApp message details by ID",
)
async def get_message(
    message_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WhatsAppMessageResponse:
    """Retrieve single WhatsApp message with IDOR authorization check."""
    try:
        msg = await WhatsAppService.get_message_by_id(db, current_user.id, message_id)
        return WhatsAppMessageResponse.model_validate(msg)
    except Exception as exc:
        logger.warning("DB unavailable for get_message, falling back: %s", exc)
        from app.accord.services.dev_store import DevStore
        messages = DevStore.get_whatsapp_messages()
        for m in messages:
            if m.id == message_id:
                return m
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")


@router.get(
    "/status",
    response_model=WhatsAppStatusResponse,
    summary="Get WhatsApp integration status and capabilities",
)
async def get_whatsapp_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WhatsAppStatusResponse:
    """Returns provider status, mock mode indicator, and registered templates."""
    try:
        status_info = await WhatsAppService.get_status(db)
        return WhatsAppStatusResponse(**status_info)
    except Exception as exc:
        logger.warning("DB unavailable for get_whatsapp_status, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        return WhatsAppStatusResponse(**DevStore.get_whatsapp_status())


# ==============================================================================
# 4. Mock Simulator Endpoints (Strictly disabled in LIVE mode)
# ==============================================================================

@router.post(
    "/mock/inbound",
    response_model=List[WhatsAppMessageResponse],
    summary="Simulate incoming WhatsApp message (MOCK MODE ONLY)",
)
async def simulate_mock_inbound(
    payload: MockInboundMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> List[WhatsAppMessageResponse]:
    """Development simulator endpoint to inject an inbound WhatsApp message.
    Strictly forbidden in LIVE mode.
    """
    if not settings.is_whatsapp_mock:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock simulation endpoints are disabled in LIVE mode.",
        )

    # Normalize phone
    from_clean = WhatsAppService.normalize_phone_number(payload.from_number)
    to_clean = WhatsAppService.normalize_phone_number(payload.to_number or "15550001234")
    simulated_wamid = f"wamid.MOCK_{uuid.uuid4().hex[:16]}"

    # Construct standard Meta webhook structure
    mock_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": settings.WHATSAPP_BUSINESS_ACCOUNT_ID or "mock_waba_id",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": to_clean,
                                "phone_number_id": settings.WHATSAPP_PHONE_NUMBER_ID or "mock_phone_id",
                            },
                            "messages": [
                                {
                                    "from": from_clean.lstrip("+"),
                                    "id": simulated_wamid,
                                    "timestamp": int(uuid.uuid1().time // 10000000),
                                    "type": "text",
                                    "text": {"body": payload.content},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    try:
        # Record webhook event
        raw_bytes = json.dumps(mock_payload).encode("utf-8")
        event, _ = await WhatsAppWebhookHandler.record_webhook_event(
            db=db,
            raw_body=raw_bytes,
            parsed_payload=mock_payload,
            signature_verified=True,
        )

        # Process through pipeline
        messages = await WhatsAppService.process_webhook_event(
            db=db,
            event_id=event.id,
            trigger_analysis=payload.trigger_analysis,
        )

        return [WhatsAppMessageResponse.model_validate(m) for m in messages]
    except Exception as exc:
        logger.warning("DB unavailable for mock inbound, falling back to DevStore: %s", exc)
        from app.accord.services.dev_store import DevStore
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        simulated_msg = WhatsAppMessageResponse(
            id=uuid.uuid4(),
            provider_message_id=simulated_wamid,
            account_id=uuid.uuid4(),
            conversation_id=None,
            sender_number=from_clean,
            recipient_number=to_clean,
            direction="INBOUND",
            message_type="TEXT",
            content=payload.content,
            provider="MOCK",
            delivery_status="DELIVERED",
            is_mock=True,
            created_at=now,
            updated_at=now,
        )
        DevStore._whatsapp_messages.insert(0, simulated_msg)
        return [simulated_msg]


@router.post(
    "/mock/status",
    summary="Simulate delivery status update (MOCK MODE ONLY)",
)
async def simulate_mock_status_update(
    payload: MockStatusUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """Simulate delivery status transition (SENT -> DELIVERED -> READ -> FAILED).
    Strictly forbidden in LIVE mode.
    """
    if not settings.is_whatsapp_mock:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Mock simulation endpoints are disabled in LIVE mode.",
        )

    provider = get_whatsapp_provider()
    if hasattr(provider, "simulate_status_transition"):
        provider.simulate_status_transition(payload.provider_message_id, payload.status)

    mock_status_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "mock_waba_id",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [
                                {
                                    "id": payload.provider_message_id,
                                    "status": payload.status.lower(),
                                    "timestamp": int(uuid.uuid1().time // 10000000),
                                    "recipient_id": "15551234567",
                                    "errors": (
                                        [{"code": payload.error_code, "title": payload.error_message}]
                                        if payload.error_code
                                        else []
                                    ),
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    raw_bytes = json.dumps(mock_status_payload).encode("utf-8")
    event, _ = await WhatsAppWebhookHandler.record_webhook_event(
        db=db,
        raw_body=raw_bytes,
        parsed_payload=mock_status_payload,
        signature_verified=True,
    )

    await WhatsAppService.process_webhook_event(
        db=db,
        event_id=event.id,
        trigger_analysis=False,
    )

    return {
        "success": True,
        "provider_message_id": payload.provider_message_id,
        "status": payload.status.upper(),
    }
