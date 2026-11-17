import re
import unicodedata
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


_EMPLOYMENT_KEYWORDS = {
    Employment.UNEMPLOYED: re.compile(
        r"\bdesempregad[oa]\b|\bsem (emprego|trabalho|ocupacao)\b|\bnao (estou )?trabalh"
    ),
    Employment.FORMAL: re.compile(
        r"\bformal\b|\bclt\b|\bcarteira (assinada|de trabalho)\b|\bregistrad[oa]\b"
        r"|\bconcursad[oa]\b|\bservidor(a)?\b|\bfuncionari[oa] publico\b"
    ),
    Employment.SELF_EMPLOYED: re.compile(
        r"\bautonom[oa]\b|\bmei\b|\bpj\b|\bfreelanc\w*\b|\b(por )?conta propria\b"
        r"|\binformal\b|\bbicos?\b|\bprofissional liberal\b|\bempresari[oa]\b"
    ),
}
_NEGATION = re.compile(r"\bnao (sou|estou|tenho)\b(?! trabalh)")
_NUMBER_WORDS = {
    "zero": 0, "nenhum": 0, "nenhuma": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2,
    "tres": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9, "dez": 10,
}  # fmt: skip
MAX_DEPENDENTS = 20


@dataclass(frozen=True)
class InterviewAnswers:
    monthly_income: Decimal
    employment: Employment
    fixed_expenses: Decimal
    dependents: int
    has_debts: bool


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def parse_employment(text: str) -> Employment | None:
    folded = _fold(text)
    if _NEGATION.search(folded):
        return None
    found = {kind for kind, pattern in _EMPLOYMENT_KEYWORDS.items() if pattern.search(folded)}
    return found.pop() if len(found) == 1 else None


def parse_dependents(text: str) -> int | None:
    folded = _fold(text)
    if re.search(r"\d[.,]\d", folded):
        return None
    if re.search(r"\b(sem|nao tenho|nao possuo)\b", folded) and not re.search(r"\d", folded):
        return 0
    numbers = {int(n) for n in re.findall(r"\d+", folded)}
    numbers |= {value for word, value in _NUMBER_WORDS.items() if re.search(rf"\b{word}\b", folded)}
    if len(numbers) != 1:
        return None
    value = numbers.pop()
    return value if value <= MAX_DEPENDENTS else None


def parse_yes_no(text: str) -> bool | None:
    folded = _fold(text).strip(" .!")
    if re.search(r"\bnao sei\b|\btalvez\b", folded):
        return None
    if re.match(r"(nao|n|nenhum[a]?|sem)\b", folded):
        return False
    if re.match(r"(sim|s|tenho|possuo|infelizmente sim)\b", folded):
        return True
    return None


def compute_score(answers: InterviewAnswers) -> int:
    income_part = answers.monthly_income / (answers.fixed_expenses + 1) * INCOME_WEIGHT
    dependents_part = DEPENDENTS_WEIGHT.get(answers.dependents, DEPENDENTS_WEIGHT_DEFAULT)
    total = (
        income_part + answers.employment.value + dependents_part + DEBT_WEIGHT[answers.has_debts]
    )
    rounded = int(total.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return max(MIN_SCORE, min(MAX_SCORE, rounded))
