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
