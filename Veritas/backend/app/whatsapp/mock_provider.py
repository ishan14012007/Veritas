import hashlib
import hmac
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.whatsapp.provider import WhatsAppBaseProvider

logger = logging.getLogger(__name__)


class MockWhatsAppProvider(WhatsAppBaseProvider):
    """Simulated WhatsApp Business provider for testing without Meta credentials.
    Generates realistic WAMID message IDs, records outbound/inbound events,
    and supports deterministic status simulations.
    """

    def __init__(
        self,
        phone_number_id: str = "mock_phone_id",
        verify_token: str = "veritas_verify_token_dev",
        app_secret: str = "mock_app_secret",
    ):
        self.phone_number_id = phone_number_id
        self.verify_token = verify_token
        self.app_secret = app_secret
        self._sent_messages: Dict[str, Dict[str, Any]] = {}
        self._status_history: Dict[str, List[Dict[str, Any]]] = {}

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def is_mock(self) -> bool:
        return True

    async def send_text_message(
        self,
        to: str,
        text: str,
        preview_url: bool = False,
        context_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Simulate sending a text message."""
        msg_id = f"wamid.MOCK_{uuid.uuid4().hex[:16]}"
        now = int(time.time())
        record = {
            "messaging_product": "whatsapp",
            "provider_message_id": msg_id,
            "recipient_number": to,
            "message_type": "TEXT",
            "content": text,
            "status": "SENT",
            "is_mock": True,
            "timestamp": now,
            "context_message_id": context_message_id,
        }
        self._sent_messages[msg_id] = record
        self._status_history.setdefault(msg_id, []).append({"status": "SENT", "timestamp": now})
        logger.info(f"[MOCK_WHATSAPP] Outbound text to {to}: '{text[:40]}...' (ID: {msg_id})")

        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": to, "wa_id": to.lstrip("+")}],
            "messages": [{"id": msg_id, "message_status": "accepted"}],
            "is_mock": True,
        }

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Simulate sending an approved WhatsApp message template."""
        msg_id = f"wamid.MOCK_{uuid.uuid4().hex[:16]}"
        now = int(time.time())
        record = {
            "messaging_product": "whatsapp",
            "provider_message_id": msg_id,
            "recipient_number": to,
            "message_type": "TEMPLATE",
            "template_name": template_name,
            "language_code": language_code,
            "components": components or [],
            "status": "SENT",
            "is_mock": True,
            "timestamp": now,
        }
        self._sent_messages[msg_id] = record
        self._status_history.setdefault(msg_id, []).append({"status": "SENT", "timestamp": now})
        logger.info(f"[MOCK_WHATSAPP] Outbound template '{template_name}' to {to} (ID: {msg_id})")

        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": to, "wa_id": to.lstrip("+")}],
            "messages": [{"id": msg_id, "message_status": "accepted"}],
            "is_mock": True,
        }

    async def send_interactive_message(
        self,
        to: str,
        interactive_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Simulate sending an interactive button or list message."""
        msg_id = f"wamid.MOCK_{uuid.uuid4().hex[:16]}"
        now = int(time.time())
        record = {
            "messaging_product": "whatsapp",
            "provider_message_id": msg_id,
            "recipient_number": to,
            "message_type": "INTERACTIVE",
            "interactive": interactive_payload,
            "status": "SENT",
            "is_mock": True,
            "timestamp": now,
        }
        self._sent_messages[msg_id] = record
        self._status_history.setdefault(msg_id, []).append({"status": "SENT", "timestamp": now})
        logger.info(f"[MOCK_WHATSAPP] Outbound interactive to {to} (ID: {msg_id})")

        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": to, "wa_id": to.lstrip("+")}],
            "messages": [{"id": msg_id, "message_status": "accepted"}],
            "is_mock": True,
        }

    def process_inbound_message(
        self,
        raw_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Parse standard Meta Graph API webhook or mock inbound payload."""
        messages: List[Dict[str, Any]] = []

        # Case 1: Standard Meta Cloud API webhook structure
        entry_list = raw_payload.get("entry", [])
        for entry in entry_list:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                recipient_number = value.get("metadata", {}).get("display_phone_number", "15550001234")
                for msg in value.get("messages", []):
                    msg_id = msg.get("id") or f"wamid.MOCK_{uuid.uuid4().hex[:16]}"
                    sender = msg.get("from", "")
                    if sender and not sender.startswith("+"):
                        sender = f"+{sender}"

                    m_type = msg.get("type", "text")
                    content = ""
                    if m_type == "text":
                        content = msg.get("text", {}).get("body", "")
                    elif m_type == "interactive":
                        # Button reply or list reply
                        interactive = msg.get("interactive", {})
                        i_type = interactive.get("type")
                        if i_type == "button_reply":
                            content = interactive.get("button_reply", {}).get("title", "")
                        elif i_type == "list_reply":
                            content = interactive.get("list_reply", {}).get("title", "")
                    elif m_type in ("image", "document", "audio", "video", "sticker"):
                        content = f"[Media: {m_type}]"
                    elif m_type == "location":
                        loc = msg.get("location", {})
                        content = f"[Location: lat={loc.get('latitude')}, lng={loc.get('longitude')}]"
                    else:
                        content = f"[Unsupported message type: {m_type}]"

                    messages.append({
                        "provider_message_id": msg_id,
                        "sender_number": sender,
                        "recipient_number": recipient_number,
                        "message_type": m_type.upper(),
                        "content": content,
                        "timestamp": msg.get("timestamp", int(time.time())),
                        "raw": msg,
                    })

        # Case 2: Simplified mock payload: {"from": "+1...", "text": "hello"}
        if not messages and ("from" in raw_payload or "sender_number" in raw_payload):
            sender = raw_payload.get("from") or raw_payload.get("sender_number")
            if sender and not sender.startswith("+"):
                sender = f"+{sender}"
            msg_id = raw_payload.get("id") or f"wamid.MOCK_{uuid.uuid4().hex[:16]}"
            content = raw_payload.get("text") or raw_payload.get("content", "")
            messages.append({
                "provider_message_id": msg_id,
                "sender_number": sender,
                "recipient_number": raw_payload.get("to") or raw_payload.get("recipient_number", "15550001234"),
                "message_type": raw_payload.get("message_type", "TEXT").upper(),
                "content": content,
                "timestamp": raw_payload.get("timestamp", int(time.time())),
                "raw": raw_payload,
            })

        return messages

    def process_status_update(
        self,
        raw_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Parse status updates (sent, delivered, read, failed)."""
        statuses: List[Dict[str, Any]] = []

        # Standard Meta Cloud API webhook structure
        entry_list = raw_payload.get("entry", [])
        for entry in entry_list:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for status_obj in value.get("statuses", []):
                    msg_id = status_obj.get("id")
                    status_val = status_obj.get("status", "").upper()
                    recipient = status_obj.get("recipient_id", "")
                    if recipient and not recipient.startswith("+"):
                        recipient = f"+{recipient}"

                    error_code = None
                    error_message = None
                    errors = status_obj.get("errors", [])
                    if errors:
                        error_code = str(errors[0].get("code", ""))
                        error_message = errors[0].get("message") or errors[0].get("title")

                    statuses.append({
                        "provider_message_id": msg_id,
                        "recipient_number": recipient,
                        "status": status_val,
                        "timestamp": status_obj.get("timestamp", int(time.time())),
                        "error_code": error_code,
                        "error_message": error_message,
                    })

                    # Update internal tracking
                    if msg_id in self._sent_messages:
                        self._sent_messages[msg_id]["status"] = status_val
                        self._status_history.setdefault(msg_id, []).append({
                            "status": status_val,
                            "timestamp": int(time.time()),
                        })

        # Simplified mock status: {"provider_message_id": "...", "status": "DELIVERED"}
        if not statuses and "status" in raw_payload and ("provider_message_id" in raw_payload or "id" in raw_payload):
            msg_id = raw_payload.get("provider_message_id") or raw_payload.get("id")
            status_val = raw_payload["status"].upper()
            statuses.append({
                "provider_message_id": msg_id,
                "recipient_number": raw_payload.get("recipient_number", ""),
                "status": status_val,
                "timestamp": raw_payload.get("timestamp", int(time.time())),
                "error_code": raw_payload.get("error_code"),
                "error_message": raw_payload.get("error_message"),
            })
            if msg_id in self._sent_messages:
                self._sent_messages[msg_id]["status"] = status_val

        return statuses

    def verify_webhook(
        self,
        hub_mode: str,
        hub_token: str,
        hub_challenge: str,
    ) -> Optional[str]:
        """Verify webhook challenge."""
        if hub_mode == "subscribe" and hub_token == self.verify_token:
            return hub_challenge
        return None

    def verify_signature(
        self,
        payload_bytes: bytes,
        signature_header: Optional[str],
    ) -> bool:
        """Validate signature. In mock mode, permits valid HMAC or mock signatures."""
        if not signature_header:
            # In mock mode, missing signature is permitted for simulated local tests
            return True

        if signature_header.startswith("mock_"):
            return True

        expected_sig = "sha256=" + hmac.new(
            key=self.app_secret.encode("utf-8"),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature_header, expected_sig)

    async def get_message_status(
        self,
        provider_message_id: str,
    ) -> Dict[str, Any]:
        """Retrieve simulated status."""
        record = self._sent_messages.get(provider_message_id)
        if record:
            return {
                "provider_message_id": provider_message_id,
                "status": record.get("status", "SENT"),
                "recipient_number": record.get("recipient_number"),
                "is_mock": True,
                "history": self._status_history.get(provider_message_id, []),
            }
        return {
            "provider_message_id": provider_message_id,
            "status": "SENT",
            "is_mock": True,
            "history": [],
        }

    def simulate_status_transition(self, provider_message_id: str, new_status: str) -> None:
        """Advance the simulated status of a message."""
        now = int(time.time())
        if provider_message_id in self._sent_messages:
            self._sent_messages[provider_message_id]["status"] = new_status.upper()
        self._status_history.setdefault(provider_message_id, []).append({
            "status": new_status.upper(),
            "timestamp": now,
        })

