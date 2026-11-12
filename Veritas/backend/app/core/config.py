from functools import lru_cache
from typing import List, Optional, Union
from pydantic import AnyHttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "VERITAS"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "veritas-dev-secret-key-change-in-production-min-32-chars"
    ENCRYPTION_MASTER_KEY: str = "01234567890123456789012345678901"

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]
    CORS_ORIGIN_REGEX: Optional[str] = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            import json
            try:
                return json.loads(v)
            except Exception:
                return [i.strip() for i in v.split(",") if i.strip()]
        return v

    def model_post_init(self, __context) -> None:
        """Configure sensible defaults for development if not explicitly overridden."""
        if self.CORS_ORIGIN_REGEX is None and (self.ENVIRONMENT == "development" or self.DEBUG):
            # Allow localhost, loopback, and RFC-1918 private LAN IP addresses on any port for development
            self.CORS_ORIGIN_REGEX = (
                r"^https?://(localhost|127\.0\.0\.1|"
                r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
                r"192\.168\.\d{1,3}\.\d{1,3}|"
                r"172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3})(:\d+)?$"
            )

    # PostgreSQL Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://veritas_user:veritas_dev_password@localhost:5432/veritas_db"
    )

    # Redis & ARQ Worker
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT Authentication
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # External Provider Configs
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-1.5-flash"

    PAYPAL_CLIENT_ID: str = "mock_client_id"
    PAYPAL_CLIENT_SECRET: str = "mock_client_secret"
    PAYPAL_BASE_URL: str = "https://api-m.sandbox.paypal.com"
    PAYPAL_API_BASE: str = "https://api-m.sandbox.paypal.com"
    PAYPAL_WEBHOOK_ID: str = ""
    PAYPAL_ENVIRONMENT: str = "sandbox"
    PAYPAL_RECEIVER_ACCOUNT: str = "merchant_sandbox@veritas.local"
    MOCK_PAYPAL: bool = True

    # WhatsApp Provider Settings
    WHATSAPP_PROVIDER: str = "mock"
    WHATSAPP_MOCK_MODE: bool = True
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID: str = ""
    WHATSAPP_APP_SECRET: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "veritas_verify_token_dev"
    WHATSAPP_GRAPH_API_VERSION: str = "v21.0"
    MOCK_WHATSAPP: bool = True

    @property
    def is_whatsapp_mock(self) -> bool:
        return (
            self.WHATSAPP_PROVIDER.lower() == "mock"
            or self.WHATSAPP_MOCK_MODE
            or self.MOCK_WHATSAPP
        )

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Return a cached instance of application settings."""
    return Settings()

