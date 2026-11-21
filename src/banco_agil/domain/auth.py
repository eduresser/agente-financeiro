import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from banco_agil.domain.cpf import is_valid_cpf, normalize_cpf

MAX_ATTEMPTS = 3

BirthLookup = Callable[[str], date | None]

CPF_DIGITS = 11
BIRTH_DIGITS = 8
MIN_BIRTH_YEAR = 1900
MIN_AGE = 18

_SEPARATORS = re.compile(r"[\s.\-/,_]+")
_ONLY_DATE_CHARS = re.compile(r"[\d\s.\-/]+")


@dataclass(frozen=True)
class AuthOutcome:
    status: Literal["authenticated", "retry", "locked"]
    attempts: int
    cpf: str | None = None


@dataclass(frozen=True)
class Credentials:
    cpf: str | None = None
    birth: date | None = None
    birth_rejected: bool = False


def _adult_cutoff(today: date) -> date:
    try:
        return today.replace(year=today.year - MIN_AGE)
    except ValueError:
        return today.replace(year=today.year - MIN_AGE, day=28)


def calendar_dates(digits: str) -> list[date]:
    if len(digits) != BIRTH_DIGITS:
        return []
    dates: list[date] = []
    for fmt in ("%d%m%Y", "%Y%m%d"):
        try:
            parsed = datetime.strptime(digits, fmt).date()
        except ValueError:
            continue
        if parsed.year >= MIN_BIRTH_YEAR:
            dates.append(parsed)
    return dates


def parse_compact_date(digits: str) -> date | None:
    cutoff = _adult_cutoff(date.today())
    return next((d for d in calendar_dates(digits) if d <= cutoff), None)


def parse_birth_date(raw: str) -> date | None:
    cleaned = raw.strip()
    if not _ONLY_DATE_CHARS.fullmatch(cleaned):
        return None
    return parse_compact_date(re.sub(r"\D", "", cleaned))


def split_joined(group: str) -> list[str]:
    if len(group) != CPF_DIGITS + BIRTH_DIGITS:
        return [group]
    for cpf, birth in (
        (group[:CPF_DIGITS], group[CPF_DIGITS:]),
        (group[BIRTH_DIGITS:], group[:BIRTH_DIGITS]),
    ):
        if is_valid_cpf(cpf) and calendar_dates(birth):
            return [cpf, birth]
    return [group]


@dataclass(frozen=True)
class DigitGroup:
    digits: str
    start: int
    end: int


def digit_spans(text: str) -> list[DigitGroup]:
    groups: list[DigitGroup] = []
    digits: list[str] = []
    start = end = 0
    for index, char in enumerate(text):
        if char.isdecimal():
            if not digits:
                start = index
            digits.append(char)
            end = index + 1
        elif not _SEPARATORS.fullmatch(char) and digits:
            groups.append(DigitGroup("".join(digits), start, end))
            digits = []
    if digits:
        groups.append(DigitGroup("".join(digits), start, end))
    return groups


def digit_groups(text: str) -> list[str]:
    return [piece for group in digit_spans(text) for piece in split_joined(group.digits)]


def extract_credentials(text: str) -> Credentials:
    cpf: str | None = None
    birth: date | None = None
    rejected = False
    for group in digit_groups(text):
        if cpf is None and len(group) == CPF_DIGITS and is_valid_cpf(group):
            cpf = group
        elif birth is None:
            birth = parse_compact_date(group)
            rejected = rejected or (birth is None and bool(calendar_dates(group)))
    return Credentials(cpf, birth, rejected and birth is None)


def register_failure(attempts: int) -> AuthOutcome:
    used = attempts + 1
    return AuthOutcome("locked" if used >= MAX_ATTEMPTS else "retry", used)


def authenticate(cpf_raw: str, birth_raw: str, lookup: BirthLookup, attempts: int) -> AuthOutcome:
    cpf = normalize_cpf(cpf_raw)
    birth = parse_birth_date(birth_raw)
    if cpf is None or birth is None:
        return register_failure(attempts)
    registered = lookup(cpf)
    if registered is None or registered != birth:
        return register_failure(attempts)
    return AuthOutcome("authenticated", attempts, cpf)
