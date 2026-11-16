import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from banco_agil.domain.cpf import normalize_cpf

MAX_ATTEMPTS = 3

BirthLookup = Callable[[str], date | None]

_DATE_IN_TEXT = re.compile(r"(?<!\d)(\d{2}/\d{2}/\d{4}|\d{4}-\d{2}-\d{2})(?!\d)")


@dataclass(frozen=True)
class AuthOutcome:
    status: Literal["authenticated", "retry", "locked"]
    attempts: int
    cpf: str | None = None


def parse_birth_date(raw: str) -> date | None:
    cleaned = raw.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def find_birth_date(text: str) -> str | None:
    match = _DATE_IN_TEXT.search(text)
    return match.group(1) if match else None


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
