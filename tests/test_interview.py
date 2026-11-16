import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from banco_agil.graph.interview_agent import make_interview_node
from banco_agil.seed import bootstrap
from banco_agil.storage import CustomerRepository
from banco_agil.tools.interview_tools import InterviewSession, build_interview_tools
from tests.fakes import ScriptedChatModel, ai, ai_tool_call

ANA = "11144477735"


@pytest.fixture
def customers_path(tmp_path: Path) -> Path:
    bootstrap(tmp_path)
    return tmp_path / "clientes.csv"


def session_for(path: Path) -> InterviewSession:
    return InterviewSession(CustomerRepository(path), ANA)


def answer_all(session: InterviewSession) -> None:
    for field, text in [
        ("monthly_income", "5000"),
        ("employment", "Formal"),
        ("fixed_expenses", "2000"),
        ("dependents", "0"),
        ("has_debts", "não"),
    ]:
        assert session.record_answer(field, text)["ok"] is True


def test_questions_come_one_at_a_time_in_fixed_order(customers_path: Path) -> None:
    session = session_for(customers_path)
    asked = []
    for field, text in [
        ("monthly_income", "5000"),
        ("employment", "formal"),
        ("fixed_expenses", "2000"),
        ("dependents", "1"),
        ("has_debts", "sim"),
    ]:
        asked.append(session.next_pending_field()["field"])
        session.record_answer(field, text)
    assert asked == ["monthly_income", "employment", "fixed_expenses", "dependents", "has_debts"]
    assert session.next_pending_field() == {"done": True}


def test_answering_out_of_order_is_refused(customers_path: Path) -> None:
    session = session_for(customers_path)
    result = session.record_answer("dependents", "2")
    assert result["ok"] is False
    assert session.answers == {}


def test_score_calculation_is_blocked_until_five_valid_answers(customers_path: Path) -> None:
    before = customers_path.read_text(encoding="utf-8")
    session = session_for(customers_path)
    session.record_answer("monthly_income", "5000")
    session.record_answer("employment", "formal")
    result = session.finish()
    assert result["ok"] is False
    assert not session.finished
    assert customers_path.read_text(encoding="utf-8") == before


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("monthly_income", "-100"),
        ("monthly_income", "muito"),
        ("employment", "freelancer"),
        ("fixed_expenses", "-1"),
        ("dependents", "1.5"),
        ("dependents", "dois"),
        ("has_debts", "talvez"),
    ],
)
def test_invalid_answer_is_rejected_and_not_stored(
    customers_path: Path, field: str, bad: str
) -> None:
    session = session_for(customers_path)
    for earlier, text in [
        ("monthly_income", "5000"),
        ("employment", "formal"),
        ("fixed_expenses", "1"),
        ("dependents", "1"),
    ]:
        if earlier == field:
            break
        session.record_answer(earlier, text)
    result = session.record_answer(field, bad)
    assert result["ok"] is False
    assert result["repeat_question"]
    assert field not in session.answers


def test_quitting_midway_leaves_scores_untouched(customers_path: Path) -> None:
    before = customers_path.read_text(encoding="utf-8")
    session = session_for(customers_path)
    session.record_answer("monthly_income", "5000")
    session.record_answer("employment", "autonomo")
    assert customers_path.read_text(encoding="utf-8") == before


def test_finishing_updates_only_the_authenticated_customer(customers_path: Path) -> None:
    before = customers_path.read_text(encoding="utf-8").splitlines()
    session = session_for(customers_path)
    answer_all(session)
    assert session.finish() == {"ok": True, "score": 575}
    after = customers_path.read_text(encoding="utf-8").splitlines()
    assert [i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b] == [1]
    assert after[1] == "11144477735,Ana Souza,1990-05-17,5000.00,575"


def test_tools_expose_no_cpf_parameter(customers_path: Path) -> None:
    tools = build_interview_tools(session_for(customers_path))
    for tool in tools:
        assert "cpf" not in tool.args


def test_agent_conducts_interview_through_tools_and_hands_back_to_credit(
    customers_path: Path,
) -> None:
    steps = [
        ("monthly_income", "5000"),
        ("employment", "formal"),
        ("fixed_expenses", "2000"),
        ("dependents", "0"),
        ("has_debts", "não"),
    ]
    script: list[AIMessage | Exception] = []
    state = {
        "customer_cpf": ANA,
        "messages": [HumanMessage(content="quero atualizar meu score")],
        "pending_limit": 9000,
    }
    node = make_interview_node(
        ScriptedChatModel(
            script=[ai_tool_call("next_pending_field", {}), ai("Qual é a sua renda mensal?")]
        ),
        CustomerRepository(customers_path),
    )
    first = node(state)  # type: ignore[arg-type]
    assert first["messages"][0].content == "Qual é a sua renda mensal?"  # type: ignore[index]
    assert "active_agent" not in first

    for field, text in steps:
        script.append(ai_tool_call("record_answer", {"field": field, "answer": text}, f"c-{field}"))
    script.append(ai_tool_call("finish_interview", {}, "c-finish"))
    state["interview"] = first["interview"]
    final = make_interview_node(
        ScriptedChatModel(script=script), CustomerRepository(customers_path)
    )(
        state  # type: ignore[arg-type]
    )
    assert final["active_agent"] == "credit"
    assert final["interview"]["score"] == 575  # type: ignore[index]
    assert "messages" not in final
    assert json.dumps(final["interview"])
