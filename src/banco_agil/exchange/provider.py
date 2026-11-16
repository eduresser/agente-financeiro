import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

import httpx

from banco_agil.logging_utils import get_logger

logger = get_logger(__name__)

DEFAULT_CURRENCY = "USD"
EXAMPLE_CURRENCIES = ["USD", "EUR", "GBP"]
TIMEOUT_SECONDS = 5.0


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


class ExchangeRateProvider(Protocol):
    def get_rate(self, currency: str | None) -> Quote: ...


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


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

    def get_rate(self, currency: str | None) -> Quote:
        code = self._resolve(currency)
        payload = self._get(f"/json/last/{code}-BRL")
        if payload is None:
            raise UnknownCurrency(self._examples())
        try:
            entry = payload[f"{code}BRL"]
            rate = Decimal(str(entry["bid"]))
            name = str(entry["name"]).split("/")[0]
        except (KeyError, TypeError, InvalidOperation) as exc:
            logger.error("exchange_invalid_payload code=%s error=%s", code, type(exc).__name__)
            raise ProviderUnavailable("invalid payload") from exc
        if rate <= 0:
            logger.error("exchange_invalid_rate code=%s", code)
            raise ProviderUnavailable("non-positive rate")
        return Quote(code, name, rate, self._clock())

    def _resolve(self, currency: str | None) -> str:
        if currency is None or not currency.strip():
            return DEFAULT_CURRENCY
        if re.fullmatch(r"[A-Za-z]{3}", currency.strip()):
            return currency.strip().upper()
        available = self._available()
        wanted = _fold(currency)
        matches = {
            pair.split("-")[0]
            for pair, label in available.items()
            if pair.endswith("-BRL") and wanted in _fold(label.split("/")[0]).split()
        }
        if len(matches) == 1:
            return matches.pop()
        if DEFAULT_CURRENCY in matches:
            return DEFAULT_CURRENCY
        raise UnknownCurrency(self._examples(available))

    def _available(self) -> dict[str, str]:
        payload = self._get("/json/available")
        if not isinstance(payload, dict):
            raise ProviderUnavailable("invalid currency list")
        return {str(key): str(value) for key, value in payload.items()}

    def _examples(self, available: dict[str, str] | None = None) -> list[str]:
        try:
            pairs = available if available is not None else self._available()
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
