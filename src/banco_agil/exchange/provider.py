import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

from banco_agil.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_CURRENCY = "USD"
DEFAULT_TARGET = "BRL"
EXAMPLE_CURRENCIES = ["USD", "EUR", "GBP"]
TIMEOUT_SECONDS = 5.0
CODE_PATTERN = re.compile(r"[A-Za-z]{3}")


class ExchangeError(Exception):
    pass


class UnknownCurrency(ExchangeError):
    def __init__(self, examples: list[str]) -> None:
        super().__init__("unknown currency")
        self.examples = examples


class ProviderUnavailable(ExchangeError):
    pass


@dataclass(frozen=True)
class Quote:
    code: str
    name: str
    rate: Decimal
    queried_at: datetime
    target: str = DEFAULT_TARGET


class ExchangeRateProvider(Protocol):
    def get_rate(self, currency: str | None, target: str | None = None) -> Quote: ...


class AwesomeApiProvider:
    def __init__(
        self,
        base_url: str,
        client: httpx.Client | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
        self._clock = clock

    def get_rate(self, currency: str | None, target: str | None = None) -> Quote:
        code = self._resolve(currency, DEFAULT_CURRENCY)
        target_code = self._resolve(target, DEFAULT_TARGET)
        found = self._pair(code, target_code)
        if found is None and DEFAULT_TARGET not in (code, target_code):
            found = self._cross(code, target_code)
        if found is None:
            raise UnknownCurrency(self._examples())
        rate, name = found
        return Quote(code, name, rate, self._clock(), target_code)

    def _pair(self, code: str, target: str) -> tuple[Decimal, str] | None:
        payload = self._get(f"/json/last/{code}-{target}")
        if payload is None:
            return None
        try:
            entry = payload[f"{code}{target}"]
            rate = Decimal(str(entry["bid"]))
            name = str(entry["name"]).split("/")[0]
        except (KeyError, TypeError, InvalidOperation) as exc:
            logger.error("exchange_invalid_payload code=%s error=%s", code, type(exc).__name__)
            raise ProviderUnavailable("invalid payload") from exc
        if rate <= 0:
            logger.error("exchange_invalid_rate code=%s", code)
            raise ProviderUnavailable("non-positive rate")
        return rate, name

    def _cross(self, code: str, target: str) -> tuple[Decimal, str] | None:
        source = self._pair(code, DEFAULT_TARGET)
        destination = self._pair(target, DEFAULT_TARGET)
        if source is None or destination is None:
            return None
        return source[0] / destination[0], source[1]

    def _resolve(self, currency: str | None, default: str) -> str:
        if currency is None or not currency.strip():
            return default
        code = currency.strip()
        if CODE_PATTERN.fullmatch(code):
            return code.upper()
        raise UnknownCurrency(self._examples())

    def _available(self) -> dict[str, str]:
        payload = self._get("/json/available")
        if not isinstance(payload, dict):
            raise ProviderUnavailable("invalid currency list")
        return {str(key): str(value) for key, value in payload.items()}

    def _examples(self) -> list[str]:
        try:
            pairs = self._available()
        except ProviderUnavailable:
            return EXAMPLE_CURRENCIES
        codes = {pair.split("-")[0] for pair in pairs if pair.endswith("-BRL")}
        examples = [code for code in EXAMPLE_CURRENCIES if code in codes]
        return examples or sorted(codes)[:3] or EXAMPLE_CURRENCIES

    def _get(self, path: str) -> dict[str, Any] | None:
        try:
            response = self._client.get(f"{self._base_url}{path}")
        except httpx.HTTPError as exc:
            logger.error("exchange_request_failed path=%s error=%s", path, type(exc).__name__)
            raise ProviderUnavailable("request failed") from exc
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            logger.error("exchange_bad_status path=%s status=%s", path, response.status_code)
            raise ProviderUnavailable(f"status {response.status_code}")
        try:
            payload = response.json()
        except ValueError as exc:
            logger.error("exchange_invalid_json path=%s", path)
            raise ProviderUnavailable("invalid json") from exc
        if not isinstance(payload, dict):
            raise ProviderUnavailable("unexpected payload")
        return payload
