from decimal import Decimal

import pytest

from banco_agil.domain.scoring import (
    Employment,
    InterviewAnswers,
    compute_score,
    parse_dependents,
    parse_employment,
    parse_yes_no,
)


def answers(
    income: str = "5000",
    employment: Employment = Employment.FORMAL,
    expenses: str = "2000",
    dependents: int = 0,
    debts: bool = False,
) -> InterviewAnswers:
    return InterviewAnswers(Decimal(income), employment, Decimal(expenses), dependents, debts)


def test_reference_interview_scores_575() -> None:
    assert compute_score(answers()) == 575


def test_score_is_capped_at_1000() -> None:
    assert compute_score(answers(income="10000", expenses="0")) == 1000


def test_score_is_floored_at_0() -> None:
    result = compute_score(
        answers(income="0", employment=Employment.UNEMPLOYED, dependents=3, debts=True)
    )
    assert result == 0


def test_three_or_more_dependents_weigh_the_same() -> None:
    assert compute_score(answers(dependents=3)) == compute_score(answers(dependents=5))
    assert compute_score(answers(dependents=2)) > compute_score(answers(dependents=3))


def test_zero_expenses_do_not_divide_by_zero() -> None:
    assert compute_score(answers(income="10", expenses="0")) == 800


def test_half_rounds_up() -> None:
    result = compute_score(answers(income="1", expenses="59", employment=Employment.UNEMPLOYED))
    assert result == 201


@pytest.mark.parametrize("text", ["Autônomo", "AUTONOMO"])
def test_employment_spelling_variations_are_equivalent(text: str) -> None:
    assert parse_employment(text) is Employment.SELF_EMPLOYED


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CLT", Employment.FORMAL),
        ("trabalho com carteira assinada", Employment.FORMAL),
        ("sou servidor público", Employment.FORMAL),
        ("MEI", Employment.SELF_EMPLOYED),
        ("trabalho por conta própria", Employment.SELF_EMPLOYED),
        ("sou freelancer", Employment.SELF_EMPLOYED),
        ("estou desempregado", Employment.UNEMPLOYED),
        ("sem emprego no momento", Employment.UNEMPLOYED),
    ],
)
def test_natural_employment_answers_are_understood(text: str, expected: Employment) -> None:
    assert parse_employment(text) is expected


@pytest.mark.parametrize(
    "text", ["astronauta", "não sou autônomo", "CLT e também MEI", "sou CLT, mas desempregado"]
)
def test_unknown_negated_or_contradictory_employment_is_rejected(text: str) -> None:
    assert parse_employment(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1", 1), ("1 filho", 1), ("dois", 2), ("tenho 3 dependentes", 3), ("nenhum", 0),
     ("sem dependentes", 0), ("0", 0)],
)  # fmt: skip
def test_natural_dependents_answers_are_understood(text: str, expected: int) -> None:
    assert parse_dependents(text) == expected


@pytest.mark.parametrize("text", ["1.5", "dois ou três", "2 filhos e 1 enteado", "muitos", "500"])
def test_ambiguous_or_implausible_dependents_are_rejected(text: str) -> None:
    assert parse_dependents(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("Sim", True), ("tenho sim", True), ("não", False), ("não tenho", False),
     ("nenhuma", False), ("sem dívidas", False)],
)  # fmt: skip
def test_natural_yes_no_answers_are_understood(text: str, expected: bool) -> None:
    assert parse_yes_no(text) is expected


def test_unknown_yes_no_is_rejected() -> None:
    assert parse_yes_no("talvez") is None
    assert parse_yes_no("não sei") is None
