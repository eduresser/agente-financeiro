from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from banco_agil.graph.credit_agent import make_credit_node
from banco_agil.graph.state import GraphState
from banco_agil.seed import bootstrap
from banco_agil.storage import CustomerRepository, LimitRequestRepository, ScoreLimitRepository
from banco_agil.tools.credit_tools import CreditService
from banco_agil.tools.interview_tools import InterviewSession
from tests.fakes import ScriptedChatModel, ai, ai_tool_call

BRUNO = "52998224725"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    bootstrap(tmp_path)
    return tmp_path


def service_for(data_dir: Path) -> CreditService:
    return CreditService(
        CustomerRepository(data_dir / "clientes.csv"),
        ScoreLimitRepository(data_dir / "score_limite.csv"),
        LimitRequestRepository(data_dir / "solicitacoes_aumento_limite.csv"),
        clock=datetime.now,
    )


def run(
    data_dir: Path, script: list[AIMessage | Exception], state: GraphState
) -> dict[str, object]:
    node = make_credit_node(ScriptedChatModel(script=script), service_for(data_dir))
    return node(state)


def base_state(text: str) -> GraphState:
    return {
        "customer_cpf": BRUNO,
        "phase": "active",
        "active_agent": "credit",
        "messages": [HumanMessage(content=text)],
    }


def test_accepted_interview_reanalyses_same_amount_with_new_score(data_dir: Path) -> None:
    rejected = run(
        data_dir,
        [
            ai_tool_call("request_limit_increase", {"new_limit": "9000"}),
            ai("Rejeitado. Quer a entrevista?"),
        ],
        base_state("quero 9000 de limite"),
    )
    assert rejected["pending_limit"] == Decimal("9000")

    state: GraphState = {**base_state("sim"), "pending_limit": rejected["pending_limit"]}  # type: ignore[typeddict-item]
    accepted = run(data_dir, [ai_tool_call("accept_interview", {})], state)
    assert accepted["active_agent"] == "interview"
    assert "messages" not in accepted

    session = InterviewSession(CustomerRepository(data_dir / "clientes.csv"), BRUNO)
    for field, text in [
        ("monthly_income", "5000"),
        ("employment", "formal"),
        ("fixed_expenses", "2000"),
        ("dependents", "0"),
        ("has_debts", "não"),
    ]:
        session.record_answer(field, text)
    assert session.finish()["score"] == 575

    after: GraphState = {**state, "interview": session.snapshot()}
    final = run(data_dir, [], after)
    assert "aprovado" in str(final["messages"][0].content).lower()  # type: ignore[index]
    assert final["pending_limit"] is None
    rows = LimitRequestRepository(data_dir / "solicitacoes_aumento_limite.csv").list_for(BRUNO)
    assert [r["status_pedido"] for r in rows] == ["rejeitado", "aprovado"]
    assert [r["novo_limite_solicitado"] for r in rows] == ["9000.00", "9000.00"]
    assert CustomerRepository(data_dir / "clientes.csv").get(BRUNO).credit_limit == Decimal(9000)  # type: ignore[union-attr]


def test_declined_interview_starts_nothing_and_clears_the_pending_request(data_dir: Path) -> None:
    state: GraphState = {**base_state("não quero"), "pending_limit": Decimal("9000")}
    result = run(
        data_dir,
        [
            ai_tool_call("decline_interview", {}),
            ai("Tudo bem! Quer encerrar ou ajudar em algo mais?"),
        ],
        state,
    )
    assert result["active_agent"] == "triage"
    assert result["pending_limit"] is None
    assert "interview" not in result
    rows = LimitRequestRepository(data_dir / "solicitacoes_aumento_limite.csv").list_for(BRUNO)
    assert rows == []
