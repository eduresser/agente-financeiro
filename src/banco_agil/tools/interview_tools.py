import json
import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool

from banco_agil.domain.scoring import MAX_DEPENDENTS, Employment, InterviewAnswers, compute_score
from banco_agil.logging_utils import get_logger, log_event
from banco_agil.storage import CustomerRepository, StorageError
from banco_agil.tools.credit_tools import UNAVAILABLE

logger = get_logger(__name__)

FIELDS = ["monthly_income", "employment", "fixed_expenses", "dependents", "has_debts"]

TOPICS = {
    "monthly_income": ("the customer's monthly income in reais", "5000"),
    "employment": ("the employment type", "FORMAL"),
    "fixed_expenses": ("the monthly fixed expenses in reais", "2000"),
    "dependents": ("the number of dependents", "2, or 0 for none"),
    "has_debts": ("whether the customer has active debts", "true or false"),
}

FORMAT_HELP = {
    "monthly_income": "A number equal to or greater than zero.",
    "employment": "FORMAL (CLT, servidor), SELF_EMPLOYED (autônomo, MEI) or UNEMPLOYED.",
    "fixed_expenses": "A number equal to or greater than zero.",
    "dependents": f"A whole number from 0 to {MAX_DEPENDENTS}.",
    "has_debts": "true or false.",
}
HELP_AFTER_FAILURES = 2


def _validate(field: str, text: str) -> object | None:
    if field in {"monthly_income", "fixed_expenses"}:
        try:
            amount = Decimal(text.strip())
        except InvalidOperation:
            return None
        return str(amount) if amount.is_finite() and amount >= 0 else None
    if field == "employment":
        return text.strip().upper() if text.strip().upper() in Employment.__members__ else None
    if field == "dependents":
        digits = text.strip()
        valid = digits.isascii() and digits.isdecimal() and int(digits) <= MAX_DEPENDENTS
        return int(digits) if valid else None
    return {"true": True, "false": False}.get(text.strip().lower())


class InterviewSession:
    def __init__(
        self, customers: CustomerRepository, cpf: str, saved: dict[str, Any] | None = None
    ) -> None:
        self._customers = customers
        self._cpf = cpf
        saved = saved or {}
        self.answers: dict[str, object] = dict(saved.get("answers", {}))
        self.score: int | None = saved.get("score")
        self.failures: dict[str, int] = dict(saved.get("failures", {}))
        self.abandoned = False

    @property
    def finished(self) -> bool:
        return self.score is not None

    def snapshot(self) -> dict[str, Any]:
        return {"answers": dict(self.answers), "score": self.score, "failures": dict(self.failures)}

    def next_pending_field(self) -> dict[str, object]:
        for field in FIELDS:
            if field not in self.answers:
                topic, example = TOPICS[field]
                remaining = sum(1 for f in FIELDS if f not in self.answers)
                return {
                    "field": field,
                    "ask_about": topic,
                    "example_answer": example,
                    "questions_left": remaining,
                }
        return {"done": True}

    def record_answer(self, field: str, answer: str) -> dict[str, object]:
        pending = self.next_pending_field()
        if pending.get("field") != field:
            return {"ok": False, "error": "Wrong order.", "next": pending}
        value = _validate(field, answer)
        if value is None:
            self.failures[field] = self.failures.get(field, 0) + 1
            result: dict[str, object] = {
                "ok": False,
                "expected": FORMAT_HELP[field],
                "ask_again_about": TOPICS[field][0],
                "example_answer": TOPICS[field][1],
                "failed_attempts": self.failures[field],
            }
            if self.failures[field] >= HELP_AFTER_FAILURES:
                result["advice"] = "Offer to pause or stop the interview instead of asking again."
            return result
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
