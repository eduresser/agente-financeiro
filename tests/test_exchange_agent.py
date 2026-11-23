from datetime import datetime
from decimal import Decimal

from langchain_core.messages import HumanMessage, ToolMessage

from banco_agil.exchange import ProviderUnavailable, Quote, UnknownCurrency
from banco_agil.graph.exchange_agent import make_exchange_node
from banco_agil.tools.exchange_tools import UNAVAILABLE, build_exchange_tools
from tests.fakes import ScriptedChatModel, ai, ai_tool_call

NOW = datetime(2026, 11, 16, 14, 30)


class FakeProvider:
    def __init__(self, result: Quote | Exception) -> None:
        self.result = result
        self.asked: list[str | None] = []

    def get_rate(self, currency: str | None, target: str | None = None) -> Quote:
        self.asked.append(currency)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def run_agent(provider: FakeProvider, asked: dict[str, str]) -> tuple[ScriptedChatModel, dict]:  # type: ignore[type-arg]
    model = ScriptedChatModel(
        script=[ai_tool_call("get_exchange_rate", asked), ai("resposta final")]
    )
    node = make_exchange_node(model, provider)
    update = node({"customer_cpf": "1", "messages": [HumanMessage(content="cotação")]})
    return model, update


def tool_outputs(model: ScriptedChatModel) -> list[str]:
    return [str(m.content) for m in model.seen[-1] if isinstance(m, ToolMessage)]


def test_agent_feeds_exact_api_value_and_query_time_to_the_answer() -> None:
    provider = FakeProvider(Quote("USD", "Dólar Americano", Decimal("5.43"), NOW))
    model, update = run_agent(provider, {})
    [output] = tool_outputs(model)
    assert "R$ 5,43" in output
    assert "Dólar Americano (USD)" in output
    assert "16/11/2026 às 14:30" in output
    assert provider.asked == [None]
    assert update["messages"][0].content == "resposta final"
    assert update["active_agent"] == "triage"


def test_requested_currency_is_passed_through_untouched() -> None:
    provider = FakeProvider(Quote("EUR", "Euro", Decimal("6.01"), NOW))
    run_agent(provider, {"currency": "EUR"})
    assert provider.asked == ["EUR"]


def test_unknown_currency_and_outage_never_produce_a_value() -> None:
    unknown = build_exchange_tools(FakeProvider(UnknownCurrency(["USD", "EUR"])))[0]
    text = unknown.invoke({"currency": "florim"})
    assert "USD, EUR" in text
    assert "R$" not in text
    down = build_exchange_tools(FakeProvider(ProviderUnavailable("down")))[0]
    assert down.invoke({}) == UNAVAILABLE
    broken = build_exchange_tools(FakeProvider(RuntimeError("boom")))[0]
    assert broken.invoke({}) == UNAVAILABLE


def test_non_brl_target_is_passed_and_shown_in_its_own_currency() -> None:
    provider = FakeProvider(Quote("EUR", "Euro", Decimal("1.1"), NOW, "USD"))
    asked: list[tuple[str | None, str | None]] = []
    original = provider.get_rate

    def spy(currency: str | None, target: str | None = None) -> Quote:
        asked.append((currency, target))
        return original(currency)

    provider.get_rate = spy  # type: ignore[method-assign]
    [tool] = build_exchange_tools(provider)[:1]
    text = tool.invoke({"currency": "EUR", "target_currency": "USD"})
    assert asked == [("EUR", "USD")]
    assert "1,1000 USD" in text
    assert "R$" not in text


def test_large_and_tiny_rates_keep_thousands_separator_and_precision() -> None:
    big = build_exchange_tools(FakeProvider(Quote("BTC", "Bitcoin", Decimal("62700"), NOW, "USD")))
    tiny = build_exchange_tools(
        FakeProvider(Quote("JPY", "Iene", Decimal("0.0048213"), NOW, "GBP"))
    )
    assert "62.700,0000 USD" in big[0].invoke({"currency": "btc", "target_currency": "usd"})
    assert "0,004821 GBP" in tiny[0].invoke({"currency": "jpy", "target_currency": "gbp"})
