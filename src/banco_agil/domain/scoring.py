from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum

INCOME_WEIGHT = Decimal(30)
MAX_SCORE = 1000
MIN_SCORE = 0
DEPENDENTS_WEIGHT = {0: 100, 1: 80, 2: 60}
DEPENDENTS_WEIGHT_DEFAULT = 30
DEBT_WEIGHT = {True: -100, False: 100}


class Employment(Enum):
    FORMAL = 300
    SELF_EMPLOYED = 200
    UNEMPLOYED = 0


MAX_DEPENDENTS = 20


@dataclass(frozen=True)
class InterviewAnswers:
    monthly_income: Decimal
    employment: Employment
    fixed_expenses: Decimal
    dependents: int
    has_debts: bool


def compute_score(answers: InterviewAnswers) -> int:
    income_part = answers.monthly_income / (answers.fixed_expenses + 1) * INCOME_WEIGHT
    dependents_part = DEPENDENTS_WEIGHT.get(answers.dependents, DEPENDENTS_WEIGHT_DEFAULT)
    total = (
        income_part + answers.employment.value + dependents_part + DEBT_WEIGHT[answers.has_debts]
    )
    rounded = int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return max(MIN_SCORE, min(MAX_SCORE, rounded))
