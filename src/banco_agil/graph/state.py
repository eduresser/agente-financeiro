from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

from banco_agil.domain.privacy import Known

Phase = Literal["auth", "active", "ended"]
AgentName = Literal["triage", "credit", "interview", "exchange"]


class GraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    phase: Phase
    auth_attempts: int
    cpf_candidate: str | None
    birth_candidate: str | None
    customer_cpf: str | None
    customer_birth: str | None
    active_agent: AgentName
    pending_limit: Decimal | None
    interview: dict[str, object]
    blocked_streak: int
    blocked_input: bool


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def known_from_state(state: GraphState) -> Known:
    if state.get("customer_cpf"):
        return Known(_parse_date(state.get("customer_birth")), logged_in=True)
    return Known(_parse_date(state.get("birth_candidate")))
