from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from banco_agil.exchange import ExchangeRateProvider
from banco_agil.graph.credit_agent import make_credit_node
from banco_agil.graph.exchange_agent import make_exchange_node
from banco_agil.graph.guard_nodes import make_input_guard_node, make_output_guard_node
from banco_agil.graph.interview_agent import make_interview_node
from banco_agil.graph.state import GraphState
from banco_agil.graph.triage import make_auth_node, make_triage_node
from banco_agil.guardrails import Guardrail
from banco_agil.storage import CustomerRepository, LimitRequestRepository, ScoreLimitRepository
from banco_agil.tools.credit_tools import CreditService

ENDED_REPLY = "Esta conversa foi encerrada. Para um novo atendimento, inicie uma nova conversa."

AGENT_NODES = ("triage", "credit", "interview", "exchange")


Node = Callable[..., dict[str, object]]


def _add(graph: StateGraph[Any, Any, Any, Any], name: str, node: Node) -> None:
    graph.add_node(name, cast(Any, node))


def closed_node(state: GraphState) -> dict[str, object]:
    return {"messages": [AIMessage(content=ENDED_REPLY)]}


def _replied_this_turn(state: GraphState) -> bool:
    for message in reversed(state.get("messages", [])):
        if isinstance(message, HumanMessage):
            return False
        if isinstance(message, AIMessage):
            return True
    return False


def route_after_input(state: GraphState) -> str:
    if state.get("blocked_input"):
        return "output_guard"
    phase = state.get("phase", "auth")
    if phase == "ended":
        return "closed"
    if phase == "auth":
        return "auth"
    return state.get("active_agent", "triage")


def route_after_node(state: GraphState) -> str:
    if state.get("phase") == "ended" or _replied_this_turn(state):
        return "output_guard"
    if state.get("phase", "auth") == "auth":
        return "output_guard"
    return state.get("active_agent", "triage")


def build_graph(
    *,
    model: BaseChatModel,
    customers: CustomerRepository,
    bands: ScoreLimitRepository,
    requests: LimitRequestRepository,
    exchange: ExchangeRateProvider,
    guardrail: Guardrail,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    clock: Callable[[], datetime] = datetime.now,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    credit_service = CreditService(customers, bands, requests, clock)
    graph: StateGraph[Any, Any, Any, Any] = StateGraph(GraphState)
    _add(graph, "input_guard", make_input_guard_node(guardrail, clock))
    _add(graph, "auth", make_auth_node(customers.birth_date_of))
    _add(graph, "triage", make_triage_node(model))
    _add(graph, "credit", make_credit_node(model, credit_service))
    _add(graph, "interview", make_interview_node(model, customers))
    _add(graph, "exchange", make_exchange_node(model, exchange))
    _add(graph, "closed", closed_node)
    _add(graph, "output_guard", make_output_guard_node(guardrail, clock))

    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges(
        "input_guard",
        route_after_input,
        ["auth", "closed", "output_guard", *AGENT_NODES],
    )
    for name in ("auth", *AGENT_NODES):
        graph.add_conditional_edges(name, route_after_node, ["output_guard", *AGENT_NODES])
    graph.add_edge("closed", "output_guard")
    graph.add_edge("output_guard", END)
    return graph.compile(checkpointer=checkpointer)
