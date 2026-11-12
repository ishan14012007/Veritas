import logging
from typing import Optional

from app.core.config import Settings, get_settings
from app.whatsapp.meta_cloud_api import MetaWhatsAppCloudProvider
from app.whatsapp.mock_provider import MockWhatsAppProvider
from app.whatsapp.provider import WhatsAppBaseProvider

logger = logging.getLogger(__name__)

_global_provider: Optional[WhatsAppBaseProvider] = None


def get_whatsapp_provider(settings: Optional[Settings] = None, force_refresh: bool = False) -> WhatsAppBaseProvider:
    """Factory creating or returning the configured WhatsApp messaging provider.
    Defaults to MockWhatsAppProvider when WHATSAPP_MOCK_MODE is enabled or credentials are unset.
    When configured for Meta in LIVE mode, strictly enforces required credentials.
    """
    global _global_provider
    cfg = settings or get_settings()

    is_live_meta = (
        cfg.WHATSAPP_PROVIDER.lower() == "meta"
        and not cfg.WHATSAPP_MOCK_MODE
        and not cfg.MOCK_WHATSAPP
    )

    if _global_provider is not None and not force_refresh:
        if _global_provider.is_mock == (not is_live_meta):
            return _global_provider

    if is_live_meta:
        logger.info("[WHATSAPP] Initializing LIVE MetaWhatsAppCloudProvider...")
        provider = MetaWhatsAppCloudProvider(
            phone_number_id=cfg.WHATSAPP_PHONE_NUMBER_ID,
            access_token=cfg.WHATSAPP_ACCESS_TOKEN,
            business_account_id=cfg.WHATSAPP_BUSINESS_ACCOUNT_ID,
            verify_token=cfg.WHATSAPP_VERIFY_TOKEN,
            app_secret=cfg.WHATSAPP_APP_SECRET,
            graph_api_version=cfg.WHATSAPP_GRAPH_API_VERSION,
        )
    else:
        logger.info("[WHATSAPP] Initializing MockWhatsAppProvider (Simulated development mode)...")
        provider = MockWhatsAppProvider(
            phone_number_id=cfg.WHATSAPP_PHONE_NUMBER_ID or "mock_phone_id",
            verify_token=cfg.WHATSAPP_VERIFY_TOKEN or "veritas_verify_token_dev",
            app_secret=cfg.WHATSAPP_APP_SECRET or "mock_app_secret",
        )

    _global_provider = provider
    return provider


def reset_whatsapp_provider() -> None:
    """Reset cached provider instance (useful in tests)."""
    global _global_provider
    _global_provider = None
