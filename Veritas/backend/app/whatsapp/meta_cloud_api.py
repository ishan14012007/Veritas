import hashlib
import hmac
import logging
import time
from typing import Any, Dict, List, Optional
import httpx
from fastapi import HTTPException, status

from app.whatsapp.provider import WhatsAppBaseProvider

logger = logging.getLogger(__name__)


class MetaWhatsAppCloudProvider(WhatsAppBaseProvider):
    """Production provider integrating Meta WhatsApp Cloud API via Meta Graph API v21+.
    Enforces strict credential validation, cryptographic HMAC-SHA256 signature verification,
    and structured error mapping without mock fallbacks.
    """

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        business_account_id: Optional[str] = None,
        verify_token: Optional[str] = None,
        app_secret: Optional[str] = None,
        graph_api_version: str = "v21.0",
        timeout_seconds: float = 20.0,
    ):
        if not phone_number_id or not phone_number_id.strip() or phone_number_id == "mock_phone_id":
            raise ValueError(
                "Meta WhatsApp Cloud API requires a valid WHATSAPP_PHONE_NUMBER_ID. "
                "Cannot initialize live Meta provider without credentials."
            )
        if not access_token or not access_token.strip() or access_token == "mock_access_token":
            raise ValueError(
                "Meta WhatsApp Cloud API requires a valid WHATSAPP_ACCESS_TOKEN. "
                "Cannot initialize live Meta provider without credentials."
            )
        if not app_secret or not app_secret.strip() or app_secret == "mock_app_secret":
            raise ValueError(
                "Meta WhatsApp Cloud API requires a valid WHATSAPP_APP_SECRET for webhook signature verification."
            )

        self.phone_number_id = phone_number_id.strip()
        self.access_token = access_token.strip()
        self.business_account_id = (business_account_id or "").strip()
        self.verify_token = (verify_token or "").strip()
        self.app_secret = app_secret.strip()
        self.graph_api_version = graph_api_version.strip()
        self.timeout_seconds = timeout_seconds

        self.base_url = f"https://graph.facebook.com/{self.graph_api_version}/{self.phone_number_id}"

    @property
    def provider_name(self) -> str:
        return "meta"

    @property
    def is_mock(self) -> bool:
        return False

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "User-Agent": "VERITAS-ACCORD-WhatsAppGateway/1.0",
        }

    def _sanitize_recipient(self, phone: str) -> str:
        """Strip leading '+' for Meta Graph API recipient parameter."""
        clean = phone.strip().replace(" ", "").replace("-", "")
        return clean.lstrip("+")

    async def _post(self, endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an asynchronous POST request to Meta Graph API."""
        url = f"{self.base_url}/{endpoint}"
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            try:
                response = await client.post(url, json=payload, headers=self._headers())
            except httpx.TimeoutException as exc:
                logger.error(f"[META_WHATSAPP] Timeout connecting to Graph API ({url}): {exc}")
                raise HTTPException(
                    status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                    detail="Meta WhatsApp Cloud API request timed out.",
                )
            except httpx.RequestError as exc:
                logger.error(f"[META_WHATSAPP] Network error contacting Graph API: {exc}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Failed to communicate with Meta WhatsApp Cloud API: {exc}",
                )

        if not response.is_success:
            err_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            error_obj = err_data.get("error", {})
            msg = error_obj.get("message") or response.text
            code = error_obj.get("code")
            subcode = error_obj.get("error_subcode")
            logger.error(f"[META_WHATSAPP] API Error {response.status_code} (code={code}, subcode={subcode}): {msg}")

            # Specific Meta error handling
            if code == 130429 or response.status_code == 429:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Meta WhatsApp Cloud API rate limit exceeded.",
                )
            if code in (190, 102):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Meta WhatsApp Cloud API access token is invalid or expired.",
                )

            raise HTTPException(
                status_code=response.status_code,
                detail=f"Meta WhatsApp Cloud API error: {msg}",
            )

        return response.json()

    async def send_text_message(
        self,
        to: str,
        text: str,
        preview_url: bool = False,
        context_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send outbound text message via Meta Graph API."""
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._sanitize_recipient(to),
            "type": "text",
            "text": {
                "preview_url": preview_url,
                "body": text,
            },
        }
        if context_message_id:
            payload["context"] = {"message_id": context_message_id}

        res = await self._post("messages", payload)
        msg_id = res.get("messages", [{}])[0].get("id", "")
        logger.info(f"[META_WHATSAPP] Outbound text dispatched to {to} (WAMID: {msg_id})")
        return res

    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Send pre-approved template message via Meta Graph API."""
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._sanitize_recipient(to),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
                "components": components or [],
            },
        }

        res = await self._post("messages", payload)
        msg_id = res.get("messages", [{}])[0].get("id", "")
        logger.info(f"[META_WHATSAPP] Outbound template '{template_name}' dispatched to {to} (WAMID: {msg_id})")
        return res

    async def send_interactive_message(
        self,
        to: str,
        interactive_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send interactive button or list message via Meta Graph API."""
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._sanitize_recipient(to),
            "type": "interactive",
            "interactive": interactive_payload,
        }

        res = await self._post("messages", payload)
        msg_id = res.get("messages", [{}])[0].get("id", "")
        logger.info(f"[META_WHATSAPP] Outbound interactive dispatched to {to} (WAMID: {msg_id})")
        return res

    def process_inbound_message(
        self,
        raw_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Parse standard Meta Cloud API inbound messages."""
        messages: List[Dict[str, Any]] = []
        entry_list = raw_payload.get("entry", [])
        for entry in entry_list:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                recipient_number = value.get("metadata", {}).get("display_phone_number", "")
                for msg in value.get("messages", []):
                    msg_id = msg.get("id", "")
                    sender = msg.get("from", "")
                    if sender and not sender.startswith("+"):
                        sender = f"+{sender}"

                    m_type = msg.get("type", "text")
                    content = ""
                    if m_type == "text":
                        content = msg.get("text", {}).get("body", "")
                    elif m_type == "interactive":
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

        return messages

    def process_status_update(
        self,
        raw_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Parse delivery status updates from Meta webhook."""
        statuses: List[Dict[str, Any]] = []
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

        return statuses

    def verify_webhook(
        self,
        hub_mode: str,
        hub_token: str,
        hub_challenge: str,
    ) -> Optional[str]:
        """Validate Meta webhook subscription challenge."""
        if hub_mode == "subscribe" and self.verify_token and hub_token == self.verify_token:
            return hub_challenge
        return None

    def verify_signature(
        self,
        payload_bytes: bytes,
        signature_header: Optional[str],
    ) -> bool:
        """Validate Meta's X-Hub-Signature-256 header using configured app secret."""
        if not signature_header or not signature_header.startswith("sha256="):
            return False

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
        """Return provider status metadata."""
        return {
            "provider_message_id": provider_message_id,
            "provider": "meta",
            "is_mock": False,
        }

