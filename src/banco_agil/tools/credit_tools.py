import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from langchain_core.tools import BaseTool, StructuredTool

from banco_agil.domain.credit_rules import format_brl, is_approved, parse_amount
from banco_agil.logging_utils import get_logger, log_event
from banco_agil.storage import (
    CustomerRepository,
    LimitRequest,
    LimitRequestRepository,
    ScoreLimitRepository,
    StorageError,
)

logger = get_logger(__name__)

UNAVAILABLE = "O serviço está momentaneamente indisponível. Tente novamente em instantes."


@dataclass(frozen=True)
class LimitDecision:
    status: Literal["approved", "rejected", "invalid", "unavailable"]
    message: str
    requested: Decimal | None = None
    current: Decimal | None = None
    ceiling: Decimal | None = None

    def as_json(self) -> str:
        return json.dumps(
            {
                "status": self.status,
                "message": self.message,
                "requested_limit": str(self.requested) if self.requested is not None else None,
                "max_allowed_limit": str(self.ceiling) if self.ceiling is not None else None,
            },
            ensure_ascii=False,
        )


class CreditService:
    def __init__(
        self,
        customers: CustomerRepository,
        bands: ScoreLimitRepository,
        requests: LimitRequestRepository,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._customers = customers
        self._bands = bands
        self._requests = requests
        self._clock = clock

    def current_limit(self, cpf: str) -> str:
        try:
            customer = self._customers.get(cpf)
        except StorageError as exc:
            log_event(logger, "limit_lookup_failed", level=logging.ERROR, cpf=cpf, error=exc)
            return UNAVAILABLE
        if customer is None:
            return UNAVAILABLE
        return f"O limite de crédito atual é {format_brl(customer.credit_limit)}."

    def request_increase(self, cpf: str, requested: Decimal | str) -> LimitDecision:
        amount = parse_amount(requested) if isinstance(requested, str) else requested
        if amount is None or amount <= 0:
            return LimitDecision(
                "invalid",
                "Informe o novo limite desejado como um valor numérico, por exemplo 8000.",
            )
        try:
            customer = self._customers.get(cpf)
            if customer is None:
                raise StorageError("authenticated customer not found")
            if amount <= customer.credit_limit:
                return LimitDecision(
                    "invalid",
                    "O valor precisa ser maior que o seu limite atual de "
                    f"{format_brl(customer.credit_limit)}.",
                    amount,
                    customer.credit_limit,
                )
            ceiling = self._bands.max_limit_for(customer.score)
            approved = is_approved(amount, ceiling)
            self._requests.append(
                LimitRequest(
                    cpf,
                    self._clock(),
                    customer.credit_limit,
                    amount,
                    "aprovado" if approved else "rejeitado",
                )
            )
            if approved:
                self._customers.update_credit_limit(cpf, amount)
        except StorageError as exc:
            log_event(logger, "limit_request_failed", level=logging.ERROR, cpf=cpf, error=exc)
            return LimitDecision("unavailable", UNAVAILABLE)
        if approved:
            return LimitDecision(
                "approved",
                f"Aumento aprovado. O novo limite é {format_brl(amount)}.",
                amount,
                customer.credit_limit,
                ceiling,
            )
        return LimitDecision(
            "rejected",
            "Aumento rejeitado: o score atual não permite esse limite. "
            f"Para o score atual, o limite máximo é {format_brl(ceiling)}.",
            amount,
            customer.credit_limit,
            ceiling,
        )


def build_credit_tools(
    service: CreditService,
    cpf: str,
    on_decision: Callable[[LimitDecision], None] | None = None,
) -> list[BaseTool]:
    def get_credit_limit() -> str:
        """Return the authenticated customer's current credit limit."""
        return service.current_limit(cpf)

    def request_limit_increase(new_limit: str) -> str:
        """Request a credit limit increase to new_limit (amount in reais)."""
        decision = service.request_increase(cpf, new_limit)
        if on_decision is not None:
            on_decision(decision)
        return decision.as_json()

    return [
        StructuredTool.from_function(get_credit_limit),
        StructuredTool.from_function(request_limit_increase),
    ]
