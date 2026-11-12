import hashlib
import json
import logging
import uuid
from typing import Any, Dict, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.whatsapp.client import get_whatsapp_provider
from app.whatsapp.models import WhatsAppWebhookEvent

logger = logging.getLogger(__name__)


class WhatsAppWebhookHandler:
    """Manages Meta/Mock WhatsApp webhook challenge verification, signature validation,
    and event deduplication.
    """

    @classmethod
    def verify_subscription(
        cls,
        hub_mode: Optional[str],
        hub_token: Optional[str],
        hub_challenge: Optional[str],
        settings: Optional[Settings] = None,
    ) -> Optional[str]:
        """Verify the webhook subscription challenge during Meta GET requests."""
        if not hub_mode or not hub_token or not hub_challenge:
            return None

        provider = get_whatsapp_provider(settings=settings)
        return provider.verify_webhook(hub_mode, hub_token, hub_challenge)

    @classmethod
    def verify_signature(
        cls,
        payload_bytes: bytes,
        signature_header: Optional[str],
        settings: Optional[Settings] = None,
    ) -> bool:
        """Validate HMAC-SHA256 signature using the active provider."""
        provider = get_whatsapp_provider(settings=settings)
        return provider.verify_signature(payload_bytes, signature_header)

    @classmethod
    async def record_webhook_event(
        cls,
        db: AsyncSession,
        raw_body: bytes,
        parsed_payload: Dict[str, Any],
        signature_verified: bool,
    ) -> Tuple[WhatsAppWebhookEvent, bool]:
        """Record the raw incoming webhook event in the database for auditing and deduplication.
        Returns: (event, is_duplicate)
        """
        idempotency_key = hashlib.sha256(raw_body).hexdigest()

        # Check existing event with same idempotency key
        stmt = select(WhatsAppWebhookEvent).where(WhatsAppWebhookEvent.idempotency_key == idempotency_key)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            logger.info(f"[WHATSAPP_WEBHOOK] Duplicate event detected (key: {idempotency_key[:12]}...)")
            return existing, True

        # Extract provider event ID or generate one
        entry_id = "unknown"
        event_type = "MESSAGES"
        if "entry" in parsed_payload and isinstance(parsed_payload["entry"], list) and parsed_payload["entry"]:
            entry_id = str(parsed_payload["entry"][0].get("id", "meta_event"))
            changes = parsed_payload["entry"][0].get("changes", [])
            if changes and "field" in changes[0]:
                event_type = changes[0]["field"].upper()
        elif "id" in parsed_payload:
            entry_id = str(parsed_payload["id"])
        elif "provider_event_id" in parsed_payload:
            entry_id = str(parsed_payload["provider_event_id"])

        event = WhatsAppWebhookEvent(
            id=uuid.uuid4(),
            provider_event_id=entry_id,
            event_type=event_type,
            signature_verified=signature_verified,
            processing_status="PENDING",
            idempotency_key=idempotency_key,
            payload=parsed_payload,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)

        return event, False
