import logging
import re
from collections.abc import Callable, Iterable

from banco_agil.domain.credit_rules import format_brl
from banco_agil.guardrails.base import ALLOWED, Direction, GuardContext, GuardResult, Judge
from banco_agil.guardrails.rules import (
    INTERNAL_MARKERS,
    advice_or_promise_present,
    agent_mention_present,
    classify_input,
    foreign_cpf_present,
    internal_leak_present,
    protected_pattern_present,
)
from banco_agil.logging_utils import get_logger
from banco_agil.storage import CustomerRepository, StorageError

logger = get_logger(__name__)

ProtectedPatterns = Callable[[str | None], Iterable[re.Pattern[str]]]


def no_protected_patterns(cpf: str | None) -> Iterable[re.Pattern[str]]:
    return ()


def other_customers_patterns(customers: CustomerRepository) -> ProtectedPatterns:
    def patterns(cpf: str | None) -> list[re.Pattern[str]]:
        try:
            everyone = customers.all()
        except StorageError:
            return []
        own = next((c for c in everyone if c.cpf == cpf), None)
        own_limit = format_brl(own.credit_limit) if own else None
        own_score = own.score if own else None
        found: list[re.Pattern[str]] = []
        for customer in everyone:
            if customer.cpf == cpf:
                continue
            limit_text = format_brl(customer.credit_limit)
            if limit_text != own_limit:
                found.append(re.compile(re.escape(limit_text)))
            if customer.score != own_score:
                found.append(re.compile(rf"score\D{{0,20}}{customer.score}(?!\d)", re.IGNORECASE))
        return found

    return patterns


class LocalGuardrail:
    def __init__(
        self,
        judge: Judge | None = None,
        protected: ProtectedPatterns = no_protected_patterns,
        internal_markers: Iterable[str] = INTERNAL_MARKERS,
    ) -> None:
        self._judge = judge
        self._protected = protected
        self._markers = list(internal_markers)

    def check_input(self, text: str, context: GuardContext) -> GuardResult:
        verdict = classify_input(text)
        if verdict == "ok":
            return ALLOWED
        if verdict == "block":
            return GuardResult(False, "prompt_injection")
        return self._judge_suspect(text, "input", "suspect_input")

    def check_output(self, text: str, context: GuardContext) -> GuardResult:
        if foreign_cpf_present(text, context.customer_cpf) or protected_pattern_present(
            text, self._protected(context.customer_cpf)
        ):
            return GuardResult(False, "foreign_data")
        if advice_or_promise_present(text):
            return GuardResult(False, "out_of_scope_content")
        if internal_leak_present(text, self._markers):
            return GuardResult(False, "internal_leak")
        if agent_mention_present(text):
            return GuardResult(False, "agent_mention")
        return ALLOWED

    def _judge_suspect(self, text: str, direction: Direction, reason: str) -> GuardResult:
        if self._judge is None:
            return GuardResult(False, reason)
        try:
            safe = self._judge.is_safe(text, direction)
        except Exception as exc:
            logger.log(logging.ERROR, "judge_failed error=%s", type(exc).__name__)
            return GuardResult(False, "judge_failed")
        return ALLOWED if safe else GuardResult(False, "judge_rejected")
