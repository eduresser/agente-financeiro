from decimal import Decimal

import pytest

from banco_agil.domain.scoring import (
    Employment,
    InterviewAnswers,
    compute_score,
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


@pytest.mark.parametrize("text", ["Autônomo", "autonomo", "AUTÔNOMO", " autonomo "])
def test_employment_spelling_variations_are_equivalent(text: str) -> None:
    assert parse_employment(text) is Employment.SELF_EMPLOYED


def test_unknown_employment_and_yes_no_are_rejected() -> None:
    assert parse_employment("freelancer") is None
    assert parse_yes_no("talvez") is None
    assert parse_yes_no("Não") is False
    assert parse_yes_no("SIM") is True
