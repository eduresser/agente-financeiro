import json
import logging
from decimal import Decimal
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from banco_agil.domain.credit_rules import parse_amount
from banco_agil.domain.scoring import (
    Employment,
    InterviewAnswers,
    compute_score,
    parse_employment,
    parse_yes_no,
)
from banco_agil.logging_utils import get_logger, log_event
from banco_agil.storage import CustomerRepository, StorageError
from banco_agil.tools.credit_tools import UNAVAILABLE

logger = get_logger(__name__)

FIELDS = ["monthly_income", "employment", "fixed_expenses", "dependents", "has_debts"]

QUESTIONS = {
    "monthly_income": "Qual é a sua renda mensal, em reais?",
    "employment": "Qual é o seu tipo de emprego: formal, autônomo ou desempregado?",
    "fixed_expenses": "Quanto você gasta por mês com despesas fixas, em reais?",
    "dependents": "Quantos dependentes você tem?",
    "has_debts": "Você possui dívidas ativas? Responda sim ou não.",
}

FORMAT_HELP = {
    "monthly_income": "Informe um valor numérico igual ou maior que zero, por exemplo 5000.",
    "employment": "Informe formal, autônomo ou desempregado.",
    "fixed_expenses": "Informe um valor numérico igual ou maior que zero, por exemplo 2000.",
    "dependents": "Informe um número inteiro igual ou maior que zero, por exemplo 2.",
    "has_debts": "Responda apenas sim ou não.",
}


def _validate(field: str, text: str) -> object | None:
    if field in {"monthly_income", "fixed_expenses"}:
        amount = parse_amount(text)
        return str(amount) if amount is not None and amount >= 0 else None
    if field == "employment":
        employment = parse_employment(text)
        return employment.name if employment is not None else None
    if field == "dependents":
        cleaned = text.strip()
        return int(cleaned) if cleaned.isdigit() else None
    return parse_yes_no(text)


class InterviewSession:
    def __init__(
        self, customers: CustomerRepository, cpf: str, saved: dict[str, Any] | None = None
    ) -> None:
        self._customers = customers
        self._cpf = cpf
        saved = saved or {}
        self.answers: dict[str, object] = dict(saved.get("answers", {}))
        self.score: int | None = saved.get("score")
        self.abandoned = False

    @property
    def finished(self) -> bool:
        return self.score is not None

    def snapshot(self) -> dict[str, Any]:
        return {"answers": dict(self.answers), "score": self.score}

    def next_pending_field(self) -> dict[str, object]:
        for field in FIELDS:
            if field not in self.answers:
                return {"field": field, "question": QUESTIONS[field]}
        return {"done": True}

    def record_answer(self, field: str, answer: str) -> dict[str, object]:
        pending = self.next_pending_field()
        if pending.get("field") != field:
            return {"ok": False, "error": "Wrong order.", "next": pending}
        value = _validate(field, answer)
        if value is None:
            return {
                "ok": False,
                "error": FORMAT_HELP[field],
                "repeat_question": QUESTIONS[field],
            }
        self.answers[field] = value
        return {"ok": True, "next": self.next_pending_field()}

    def finish(self) -> dict[str, object]:
        if self.finished:
            return {"ok": True, "score": self.score}
        if not all(field in self.answers for field in FIELDS):
            return {
                "ok": False,
                "error": "Interview incomplete.",
                "next": self.next_pending_field(),
            }
        score = compute_score(
            InterviewAnswers(
                Decimal(str(self.answers["monthly_income"])),
                Employment[str(self.answers["employment"])],
                Decimal(str(self.answers["fixed_expenses"])),
                int(str(self.answers["dependents"])),
                bool(self.answers["has_debts"]),
            )
        )
        try:
            self._customers.update_score(self._cpf, score)
        except StorageError as exc:
            log_event(logger, "score_update_failed", level=logging.ERROR, cpf=self._cpf, error=exc)
            return {"ok": False, "error": UNAVAILABLE}
        self.score = score
        return {"ok": True, "score": score}


def build_interview_tools(session: InterviewSession) -> list[BaseTool]:
    def next_pending_field() -> str:
        """Return the next interview question to ask the customer, one at a time."""
        return json.dumps(session.next_pending_field(), ensure_ascii=False)

    def record_answer(field: str, answer: str) -> str:
        """Validate and store the customer's answer for the pending field."""
        return json.dumps(session.record_answer(field, answer), ensure_ascii=False)

    def finish_interview() -> str:
        """Calculate and save the new score once all five answers are valid."""
        return json.dumps(session.finish(), ensure_ascii=False)

    def abandon_interview() -> str:
        """Cancel the interview when the customer gives up. No score is changed."""
        session.abandoned = True
        return json.dumps({"ok": True})

    return [
        StructuredTool.from_function(abandon_interview),
        StructuredTool.from_function(next_pending_field),
        StructuredTool.from_function(record_answer),
        StructuredTool.from_function(finish_interview),
    ]
