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
MAX_BIRTH_YEAR = 2100

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


def _parse_compact_date(digits: str) -> date | None:
    if len(digits) != BIRTH_DIGITS:
        return None
    for fmt in ("%d%m%Y", "%Y%m%d"):
        try:
            parsed = datetime.strptime(digits, fmt).date()
        except ValueError:
            continue
        if MIN_BIRTH_YEAR <= parsed.year <= MAX_BIRTH_YEAR:
            return parsed
    return None


def parse_birth_date(raw: str) -> date | None:
    cleaned = raw.strip()
    if not _ONLY_DATE_CHARS.fullmatch(cleaned):
        return None
    return _parse_compact_date(re.sub(r"\D", "", cleaned))


def _split_joined(group: str) -> list[str]:
    if len(group) != CPF_DIGITS + BIRTH_DIGITS:
        return [group]
    for cpf, birth in (
        (group[:CPF_DIGITS], group[CPF_DIGITS:]),
        (group[BIRTH_DIGITS:], group[:BIRTH_DIGITS]),
    ):
        if is_valid_cpf(cpf) and _parse_compact_date(birth):
            return [cpf, birth]
    return [group]


def digit_groups(text: str) -> list[str]:
    return [
        piece
        for group in re.findall(r"\d+", _SEPARATORS.sub("", text))
        for piece in _split_joined(group)
    ]


def extract_credentials(text: str) -> Credentials:
    cpf: str | None = None
    birth: date | None = None
    for group in digit_groups(text):
        if cpf is None and len(group) == CPF_DIGITS and is_valid_cpf(group):
            cpf = group
        elif birth is None:
            birth = _parse_compact_date(group)
    return Credentials(cpf, birth)


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
