from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class WhatsAppBaseProvider(ABC):
    """Abstract provider interface for WhatsApp Business messaging platforms."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the provider (e.g., 'mock' or 'meta')."""
        pass

    @property
    @abstractmethod
    def is_mock(self) -> bool:
        """Whether this provider operates in simulated mock mode."""
        pass

    @abstractmethod
    async def send_text_message(
        self,
        to: str,
        text: str,
        preview_url: bool = False,
        context_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a freeform text message to a recipient phone number."""
        pass

    @abstractmethod
    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "en_US",
        components: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Send a pre-approved template message outside the 24-hour service window."""
        pass

    @abstractmethod
    async def send_interactive_message(
        self,
        to: str,
        interactive_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Send an interactive button or list message."""
        pass

    @abstractmethod
    def process_inbound_message(
        self,
        raw_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Normalize inbound webhook payload into standardized message dictionaries.
        Each dictionary contains:
        {
            "provider_message_id": str,
            "sender_number": str,
            "recipient_number": str,
            "message_type": str,
            "content": str,
            "timestamp": int/str,
            "raw": Dict,
        }
        """
        pass

    @abstractmethod
    def process_status_update(
        self,
        raw_payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Normalize message delivery status updates from webhook payload.
        Each dictionary contains:
        {
            "provider_message_id": str,
            "recipient_number": str,
            "status": str (SENT, DELIVERED, READ, FAILED),
            "timestamp": int/str,
            "error_code": Optional[str],
            "error_message": Optional[str],
        }
        """
        pass

    @abstractmethod
    def verify_webhook(
        self,
        hub_mode: str,
        hub_token: str,
        hub_challenge: str,
    ) -> Optional[str]:
        """Verify webhook subscription challenge during GET webhook verification."""
        pass

    @abstractmethod
    def verify_signature(
        self,
        payload_bytes: bytes,
        signature_header: Optional[str],
    ) -> bool:
        """Validate HMAC-SHA256 signature on incoming webhook POST."""
        pass

    @abstractmethod
    async def get_message_status(
        self,
        provider_message_id: str,
    ) -> Dict[str, Any]:
        """Retrieve the delivery status of a sent message."""
        pass

