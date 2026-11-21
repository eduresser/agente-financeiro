import logging
import re
from collections.abc import Callable, Iterable
from decimal import Decimal

from banco_agil.domain.privacy import redact_sensitive
from banco_agil.guardrails.base import ALLOWED, Direction, GuardContext, GuardResult, Judge
from banco_agil.guardrails.rules import (
    INTERNAL_MARKERS,
    Protected,
    advice_or_promise_present,
    agent_mention_present,
    classify_input,
    external_link_present,
    foreign_cpf_present,
    internal_leak_present,
    protected_pattern_present,
)
from banco_agil.logging_utils import get_logger
from banco_agil.storage import CustomerRepository, ScoreLimitRepository, StorageError

logger = get_logger(__name__)

ProtectedPatterns = Callable[[str | None], Iterable[Protected | re.Pattern[str]]]

_NAME_MIN_LENGTH = 4


def no_protected_patterns(cpf: str | None) -> Iterable[Protected | re.Pattern[str]]:
    return ()


def _typed_amount_pattern(value: Decimal) -> re.Pattern[str]:
    whole = int(value)
    number = "(?:" + "|".join({re.escape(f"{whole:,}".replace(",", ".")), str(whole)}) + ")"
    forms = [rf"(?<![\d.,]){number}(?:,\d{{2}})?(?!\d)"]
    if whole >= 1000 and whole % 1000 == 0:
        forms.append(rf"(?<!\d){whole // 1000}\s*mil\b")
    return re.compile("|".join(forms), re.IGNORECASE)


def _amount_pattern(value: Decimal) -> re.Pattern[str]:
    whole = int(value)
    number = "(?:" + "|".join({re.escape(f"{whole:,}".replace(",", ".")), str(whole)}) + ")"
    cents = r"(?:,\d{2})?"
    forms = [rf"R\$\s*{number}{cents}(?!\d)", rf"(?<![\d.,]){number}{cents}\s+reais\b"]
    if whole >= 1000 and whole % 1000 == 0:
        mil = rf"{whole // 1000}\s*mil"
        forms += [rf"R\$\s*{mil}\b", rf"(?<!\d){mil}\s+reais\b"]
    return re.compile("|".join(forms), re.IGNORECASE)


def _score_pattern(score: int) -> re.Pattern[str]:
    return re.compile(
        rf"(?:score|pontua[cç][ãa]o|pontos?|nota)\D{{0,25}}{score}(?!\d)"
        rf"|(?<![\d.,]){score}\s+pontos\b",
        re.IGNORECASE,
    )


def _ceiling_of(bands: ScoreLimitRepository, score: int) -> int | None:
    try:
        return int(bands.max_limit_for(score))
    except StorageError:
        return None


def other_customers_patterns(
    customers: CustomerRepository, bands: ScoreLimitRepository | None = None
) -> ProtectedPatterns:
    def patterns(cpf: str | None) -> list[Protected]:
        try:
            everyone = customers.all()
        except StorageError:
            return []
        own = next((c for c in everyone if c.cpf == cpf), None)
        own_limit = int(own.credit_limit) if own else None
        own_ceiling = _ceiling_of(bands, own.score) if own and bands else None
        own_score = own.score if own else None
        own_first = own.name.split()[0].lower() if own and own.name else None
        found: list[Protected] = []
        for customer in everyone:
            if customer.cpf == cpf:
                continue
            if int(customer.credit_limit) not in (own_limit, own_ceiling):
                found.append(
                    Protected(
                        _amount_pattern(customer.credit_limit),
                        user_pattern=_typed_amount_pattern(customer.credit_limit),
                    )
                )
            if customer.score != own_score:
                found.append(Protected(_score_pattern(customer.score)))
            if customer.name:
                found.append(Protected(re.compile(rf"\b{re.escape(customer.name)}\b", re.I), False))
                first = customer.name.split()[0]
                if len(first) >= _NAME_MIN_LENGTH and first.lower() != own_first:
                    found.append(Protected(re.compile(rf"\b{re.escape(first)}\b", re.I), False))
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
        return self._judge_suspect(text, "input", "suspect_input", context)

    def check_output(self, text: str, context: GuardContext) -> GuardResult:
        if foreign_cpf_present(text, context.customer_cpf) or protected_pattern_present(
            text, self._protected(context.customer_cpf), context.user_text
        ):
            return GuardResult(False, "foreign_data")
        if external_link_present(text):
            return GuardResult(False, "external_link")
        if advice_or_promise_present(text):
            return GuardResult(False, "out_of_scope_content")
        if internal_leak_present(text, self._markers):
            return GuardResult(False, "internal_leak")
        if agent_mention_present(text):
            return GuardResult(False, "agent_mention")
        return ALLOWED

    def _judge_suspect(
        self, text: str, direction: Direction, reason: str, context: GuardContext
    ) -> GuardResult:
        if self._judge is None:
            return GuardResult(False, reason)
        try:
            safe = self._judge.is_safe(redact_sensitive(text, context.known), direction)
        except Exception as exc:
            logger.log(logging.ERROR, "judge_failed error=%s", type(exc).__name__)
            return GuardResult(False, "judge_failed")
        return ALLOWED if safe else GuardResult(False, "judge_rejected")
