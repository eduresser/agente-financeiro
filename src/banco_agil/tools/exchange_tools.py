import logging

from langchain_core.tools import BaseTool, StructuredTool

from banco_agil.domain.credit_rules import format_brl
from banco_agil.exchange import (
    ExchangeRateProvider,
    ProviderUnavailable,
    UnknownCurrency,
)
from banco_agil.logging_utils import get_logger

logger = get_logger(__name__)

UNAVAILABLE = "A cotação está indisponível no momento. Tente novamente mais tarde, por favor."


def describe_rate(provider: ExchangeRateProvider, currency: str | None) -> str:
    try:
        quote = provider.get_rate(currency)
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
    return f"{quote.name} ({quote.code}): {format_brl(quote.rate)}, consultada em {when}."


def build_exchange_tools(provider: ExchangeRateProvider) -> list[BaseTool]:
    def get_exchange_rate(currency: str | None = None) -> str:
        """Get the current rate in reais of a currency given by name or code (default dollar)."""
        return describe_rate(provider, currency)

    return [StructuredTool.from_function(get_exchange_rate)]
