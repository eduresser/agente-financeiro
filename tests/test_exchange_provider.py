import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest

from banco_agil.exchange import AwesomeApiProvider, ProviderUnavailable, UnknownCurrency

NOW = datetime(2026, 11, 16, 14, 30, 0)
AVAILABLE = {
    "USD-BRL": "Dólar Americano/Real Brasileiro",
    "CAD-BRL": "Dólar Canadense/Real Brasileiro",
    "EUR-BRL": "Euro/Real Brasileiro",
    "GBP-BRL": "Libra Esterlina/Real Brasileiro",
    "BTC-USD": "Bitcoin/Dólar Americano",
}


def quote_body(
    code: str, bid: str = "5.43", name: str = "Dólar Americano/Real Brasileiro"
) -> dict[str, Any]:
    return {f"{code}BRL": {"code": code, "codein": "BRL", "name": name, "bid": bid}}


Handler = Callable[[httpx.Request], httpx.Response]


def provider(handler: Handler, calls: list[str] | None = None) -> AwesomeApiProvider:
    def wrapped(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request.url.path)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(wrapped))
    return AwesomeApiProvider("https://api.test", client=client, clock=lambda: NOW)


def standard_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/json/available":
        return httpx.Response(200, json=AVAILABLE)
    code = path.rsplit("/", 1)[1].split("-")[0]
    if code == "USD":
        return httpx.Response(200, json=quote_body("USD"))
    if code == "EUR":
        return httpx.Response(200, json=quote_body("EUR", "6.01", "Euro/Real Brasileiro"))
    return httpx.Response(404, json={"status": 404, "code": "CoinNotExists"})


@pytest.mark.parametrize("asked", ["EUR", "eur", " Eur "])
def test_currency_code_is_case_and_space_insensitive(asked: str) -> None:
    quote = provider(standard_handler).get_rate(asked)
    assert (quote.code, quote.rate) == ("EUR", Decimal("6.01"))


def test_quote_carries_exact_api_value_currency_and_query_time() -> None:
    quote = provider(standard_handler).get_rate("USD")
    assert quote.rate == Decimal("5.43")
    assert quote.name == "Dólar Americano"
    assert quote.queried_at == NOW


def test_missing_currency_defaults_to_dollar() -> None:
    assert provider(standard_handler).get_rate(None).code == "USD"


@pytest.mark.parametrize("asked", ["florim", "bitcoin", "dólar"])
def test_unknown_currency_or_name_lists_available_examples(asked: str) -> None:
    with pytest.raises(UnknownCurrency) as exc:
        provider(standard_handler).get_rate(asked)
    assert exc.value.examples == ["USD", "EUR", "GBP"]


def test_server_error_timeout_and_garbage_are_all_unavailable(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("slow", request=request)

    cases: dict[str, Handler] = {
        "server error": lambda r: httpx.Response(503),
        "timeout": timeout,
        "not json": lambda r: httpx.Response(200, text="<html>oops</html>"),
        "no bid": lambda r: httpx.Response(200, json={"USDBRL": {"code": "USD"}}),
        "bid not a number": lambda r: httpx.Response(200, json=quote_body("USD", "abc")),
        "zero bid": lambda r: httpx.Response(200, json=quote_body("USD", "0")),
    }
    for label, handler in cases.items():
        with caplog.at_level(logging.ERROR), pytest.raises(ProviderUnavailable):
            provider(handler).get_rate("USD")
        assert caplog.text, label
        caplog.clear()


def test_plain_code_costs_a_single_request() -> None:
    calls: list[str] = []
    provider(standard_handler, calls).get_rate("EUR")
    assert calls == ["/json/last/EUR-BRL"]


def cross_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/json/available":
        return httpx.Response(200, json=AVAILABLE)
    if path == "/json/last/EUR-USD":
        return httpx.Response(200, json=quote_pair("EUR", "USD", "1.10", "Euro/Dólar Americano"))
    return standard_handler(request)


def brl_pairs_only(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("-BRL") or request.url.path == "/json/available":
        return standard_handler(request)
    return httpx.Response(404, json={"status": 404})


def quote_pair(code: str, target: str, bid: str, name: str) -> dict[str, Any]:
    return {f"{code}{target}": {"code": code, "codein": target, "name": name, "bid": bid}}


def test_target_currency_uses_the_direct_pair_when_the_api_has_it() -> None:
    quote = provider(cross_handler).get_rate("EUR", "USD")
    assert (quote.code, quote.target, quote.rate, quote.name) == (
        "EUR",
        "USD",
        Decimal("1.10"),
        "Euro",
    )


def test_target_currency_falls_back_to_a_cross_rate_through_brl() -> None:
    calls: list[str] = []
    quote = provider(brl_pairs_only, calls).get_rate("EUR", "USD")
    assert quote.target == "USD"
    assert quote.rate == Decimal("6.01") / Decimal("5.43")
    assert calls == ["/json/last/EUR-USD", "/json/last/EUR-BRL", "/json/last/USD-BRL"]


def test_target_code_is_normalized_and_unknown_target_is_reported() -> None:
    assert provider(cross_handler).get_rate("EUR", "usd").target == "USD"
    with pytest.raises(UnknownCurrency):
        provider(brl_pairs_only).get_rate("EUR", "XYZ")


def test_default_clock_reports_brasilia_time_three_hours_behind_utc() -> None:
    from datetime import UTC, datetime

    from banco_agil.clock import now_brasilia

    utc_now = datetime.now(UTC).replace(tzinfo=None)
    offset = utc_now - now_brasilia()
    assert abs(offset.total_seconds() - 3 * 3600) < 5
