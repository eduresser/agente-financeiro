from datetime import date

import pytest

from banco_agil.domain.auth import (
    authenticate,
    find_birth_date,
    parse_birth_date,
    register_failure,
)
from banco_agil.domain.cpf import find_cpf, normalize_cpf

CUSTOMERS = {"12345678909": date(1990, 5, 17)}


def lookup(cpf: str) -> date | None:
    return CUSTOMERS.get(cpf)


@pytest.mark.parametrize("cpf", ["123.456.789-09", "12345678909", " 123.456.78909 "])
@pytest.mark.parametrize("birth", ["17/05/1990", "1990-05-17"])
def test_every_accepted_format_combination_authenticates(cpf: str, birth: str) -> None:
    outcome = authenticate(cpf, birth, lookup, attempts=0)
    assert outcome.status == "authenticated"
    assert outcome.cpf == "12345678909"


def test_wrong_cpf_and_wrong_birth_date_are_indistinguishable() -> None:
    wrong_birth = authenticate("123.456.789-09", "01/01/2000", lookup, attempts=0)
    unknown_cpf = authenticate("529.982.247-25", "17/05/1990", lookup, attempts=0)
    assert wrong_birth == unknown_cpf
    assert wrong_birth.status == "retry"
    assert wrong_birth.cpf is None


def test_third_consecutive_failure_locks_the_session() -> None:
    first = authenticate("123.456.789-09", "01/01/2000", lookup, attempts=0)
    second = authenticate("123.456.789-09", "01/01/2000", lookup, attempts=first.attempts)
    third = authenticate("123.456.789-09", "01/01/2000", lookup, attempts=second.attempts)
    assert [first.status, second.status, third.status] == ["retry", "retry", "locked"]
    assert third.attempts == 3


def test_malformed_cpf_consumes_an_attempt() -> None:
    assert normalize_cpf("123.456.789") is None
    outcome = authenticate("123.456.789", "17/05/1990", lookup, attempts=1)
    assert outcome.status == "retry"
    assert outcome.attempts == 2
    assert register_failure(2).status == "locked"


def test_success_on_last_attempt_still_authenticates() -> None:
    outcome = authenticate("12345678909", "17/05/1990", lookup, attempts=2)
    assert outcome.status == "authenticated"


@pytest.mark.parametrize("raw", ["31/02/1990", "1990/05/17", "17-05-1990", "abc", ""])
def test_impossible_or_unknown_date_formats_are_rejected(raw: str) -> None:
    assert parse_birth_date(raw) is None
    assert authenticate("12345678909", raw, lookup, attempts=0).status == "retry"


def test_values_are_found_inside_free_text() -> None:
    assert find_cpf("meu cpf é 123.456.789-09, obrigado") == "12345678909"
    assert find_birth_date("nasci em 17/05/1990") == "17/05/1990"
    assert find_cpf("tenho 12345 reais") is None
    assert find_cpf("1234567890912") is None


@pytest.mark.parametrize("cpf", ["123.456.789-00", "111.111.111-11", "529.982.247-24"])
def test_cpf_with_wrong_check_digits_is_rejected_and_costs_an_attempt(cpf: str) -> None:
    assert normalize_cpf(cpf) is None
    assert find_cpf(f"meu cpf {cpf}") is None
    assert authenticate(cpf, "17/05/1990", lookup, attempts=0).attempts == 1


def test_valid_check_digits_are_accepted() -> None:
    assert normalize_cpf("529.982.247-25") == "52998224725"
    assert normalize_cpf("111.444.777-35") == "11144477735"
