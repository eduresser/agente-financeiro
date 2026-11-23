import logging

from langchain_core.tools import BaseTool, StructuredTool

from banco_agil.domain.money import format_brl
from banco_agil.exchange import (
    ExchangeRateProvider,
    ProviderUnavailable,
    Quote,
    UnknownCurrency,
)
from banco_agil.exchange.provider import DEFAULT_TARGET
from banco_agil.logging_utils import get_logger

logger = get_logger(__name__)

UNAVAILABLE = "A cotação está indisponível no momento. Tente novamente mais tarde, por favor."


def format_rate(quote: Quote) -> str:
    if quote.target == DEFAULT_TARGET:
        return format_brl(quote.rate)
    decimals = 4 if quote.rate >= 1 else 6
    number = f"{quote.rate:,.{decimals}f}".translate(str.maketrans(",.", ".,"))
    return f"{number} {quote.target}"


def describe_rate(
    provider: ExchangeRateProvider, currency: str | None, target: str | None = None
) -> str:
    try:
        quote = provider.get_rate(currency, target)
    except UnknownCurrency as exc:
        return (
            f"Não encontrei essa moeda. Exemplos de moedas disponíveis: {', '.join(exc.examples)}."
        )
    except ProviderUnavailable:
        return UNAVAILABLE
    except Exception as exc:
        logger.log(logging.ERROR, "exchange_unexpected_error error=%s", type(exc).__name__)
        return UNAVAILABLE
    when = quote.queried_at.strftime("%d/%m/%Y às %H:%M")
    return f"{quote.name} ({quote.code}): {format_rate(quote)}, consultada em {when}."


def build_exchange_tools(provider: ExchangeRateProvider) -> list[BaseTool]:
    def get_exchange_rate(currency: str | None = None, target_currency: str | None = None) -> str:
        """Get the current rate of a currency (default dollar) given by its 3-letter ISO code,
        e.g. USD or EUR, in the target currency (default reais, BRL)."""
        return describe_rate(provider, currency, target_currency)

    return [StructuredTool.from_function(get_exchange_rate)]
