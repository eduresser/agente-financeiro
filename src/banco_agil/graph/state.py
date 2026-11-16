from decimal import Decimal
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

Phase = Literal["auth", "active", "ended"]
AgentName = Literal["triage", "credit", "interview", "exchange"]


class GraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    phase: Phase
    auth_attempts: int
    cpf_candidate: str | None
    customer_cpf: str | None
    active_agent: AgentName
    pending_limit: Decimal | None
    interview: dict[str, object]
    blocked_streak: int
