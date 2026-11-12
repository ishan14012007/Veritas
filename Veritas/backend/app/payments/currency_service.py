"""
VERITAS Currency Conversion Service
Provides live, reliable exchange rate lookup and conversion for PayPal checkout compatibility.
Preserves original transaction records in INR while ensuring compliance with PayPal's supported currencies.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Dict, Optional, Tuple
import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Official list of currencies supported by PayPal REST API Checkout
PAYPAL_SUPPORTED_CURRENCIES = {
    "AUD", "BRL", "CAD", "CNY", "CZK", "DKK", "EUR", "HKD", "HUF", "ILS",
    "JPY", "MYR", "MXN", "TWD", "NZD", "NOK", "PHP", "PLN", "GBP", "SGD",
    "SEK", "CHF", "THB", "USD"
}

# Reliable fallback reference rates (per 1 USD) if both live APIs are temporarily unreachable
FALLBACK_USD_RATES = {
    "INR": Decimal("93.85"),
    "EUR": Decimal("0.95"),
    "GBP": Decimal("0.79"),
    "CAD": Decimal("1.41"),
    "AUD": Decimal("1.54"),
    "JPY": Decimal("154.50"),
}


class CurrencyConversionResult(BaseModel):
    original_amount: Decimal
    original_currency: str
    paypal_amount: Decimal
    paypal_currency: str
    exchange_rate: Decimal
    is_converted: bool


class CurrencyService:
    """Singleton service to retrieve live exchange rates and convert unsupported currencies for PayPal."""

    _instance: Optional["CurrencyService"] = None
    _cached_rates: Dict[str, Decimal] = {}
    _last_fetched: Optional[datetime] = None
    _cache_ttl_seconds: int = 3600  # 1 hour cache

    @classmethod
    def get_instance(cls) -> "CurrencyService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def is_paypal_supported(cls, currency: Optional[str]) -> bool:
        if not currency:
            return False
        return currency.strip().upper() in PAYPAL_SUPPORTED_CURRENCIES

    async def get_live_rates(self) -> Dict[str, Decimal]:
        """Fetch live USD exchange rates from reliable public financial endpoints."""
        now = datetime.now(timezone.utc)
        if (
            self._cached_rates
            and self._last_fetched
            and (now - self._last_fetched).total_seconds() < self._cache_ttl_seconds
        ):
            return self._cached_rates

        rates: Dict[str, Decimal] = {}

        # 1. Primary: open.er-api.com
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get("https://open.er-api.com/v6/latest/USD")
                if res.status_code == 200:
                    data = res.json()
                    raw_rates = data.get("rates", {})
                    for code, val in raw_rates.items():
                        try:
                            rates[code.upper()] = Decimal(str(val))
                        except Exception:
                            pass
                    if "INR" in rates:
                        self._cached_rates = rates
                        self._last_fetched = now
                        logger.info(f"Updated live exchange rates via open.er-api (1 USD = {rates['INR']} INR)")
                        return rates
        except Exception as e:
            logger.warning(f"Primary exchange rate API failed: {e}. Trying fallback source.")

        # 2. Secondary: api.frankfurter.dev
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get("https://api.frankfurter.dev/v1/latest?base=USD")
                if res.status_code == 200:
                    data = res.json()
                    raw_rates = data.get("rates", {})
                    for code, val in raw_rates.items():
                        try:
                            rates[code.upper()] = Decimal(str(val))
                        except Exception:
                            pass
                    if "INR" in rates:
                        self._cached_rates = rates
                        self._last_fetched = now
                        logger.info(f"Updated live exchange rates via frankfurter (1 USD = {rates['INR']} INR)")
                        return rates
        except Exception as e:
            logger.warning(f"Secondary exchange rate API failed: {e}. Using cached or reference rates.")

        # 3. Fallback: Previously cached rates or reference rates
        if self._cached_rates:
            return self._cached_rates

        logger.info("Using baseline reference exchange rates.")
        self._cached_rates = dict(FALLBACK_USD_RATES)
        self._last_fetched = now
        return self._cached_rates

    async def convert_for_paypal(
        self,
        amount: Decimal,
        currency: str,
        target_currency: str = "USD",
    ) -> CurrencyConversionResult:
        """Convert an amount from an unsupported currency to a PayPal-compatible currency (default USD).
        Preserves original amount and currency untouched.
        """
        curr = currency.strip().upper() if currency else "USD"
        orig_amount = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # If already natively supported by PayPal, no conversion required
        if self.is_paypal_supported(curr):
            return CurrencyConversionResult(
                original_amount=orig_amount,
                original_currency=curr,
                paypal_amount=orig_amount,
                paypal_currency=curr,
                exchange_rate=Decimal("1.00"),
                is_converted=False,
            )

        # Unsupported currency (e.g., INR): convert to USD
        rates = await self.get_live_rates()
        rate = rates.get(curr, FALLBACK_USD_RATES.get(curr, Decimal("93.85")))

        if rate <= Decimal("0.00"):
            rate = Decimal("93.85")

        converted = (orig_amount / rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # Ensure minimum payable amount is 0.01
        if converted <= Decimal("0.00"):
            converted = Decimal("0.01")

        logger.info(
            f"PayPal currency conversion applied: {orig_amount} {curr} -> "
            f"{converted} {target_currency} (Rate: 1 {target_currency} = {rate} {curr})"
        )

        return CurrencyConversionResult(
            original_amount=orig_amount,
            original_currency=curr,
            paypal_amount=converted,
            paypal_currency=target_currency,
            exchange_rate=rate.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            is_converted=True,
        )


def get_currency_service() -> CurrencyService:
    return CurrencyService.get_instance()

