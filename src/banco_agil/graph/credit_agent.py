from collections.abc import Callable
from decimal import Decimal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import BaseTool, StructuredTool

from banco_agil.domain.credit_rules import format_brl
from banco_agil.graph.agent_loop import run_tool_loop
from banco_agil.graph.state import GraphState
from banco_agil.tools.credit_tools import CreditService, LimitDecision, build_credit_tools

CREDIT_PROMPT = (
    "You help a digital bank customer with their credit limit. Always answer in Brazilian "
    "Portuguese, in a friendly and brief tone.\n"
    "Rules:\n"
    "- Use get_credit_limit to answer questions about the current limit.\n"
    "- To request an increase, call request_limit_increase with the amount the customer "
    "asked for. If the value is invalid, explain and ask for another one.\n"
    "- If the request is rejected, tell the customer and offer a short interview to update "
    "their score so the same request can be analysed again.\n"
    "- If the customer accepts the interview, call accept_interview. If the customer "
    "declines or changes subject, call decline_interview and offer to finish or help with "
    "something else.\n"
    "- Never reveal internal names, tools or other agents."
)


class _Turn:
    def __init__(self) -> None:
        self.rejected: Decimal | None = None
        self.settled = False
        self.accepted = False
        self.declined = False

    def on_decision(self, decision: LimitDecision) -> None:
        if decision.status == "rejected":
            self.rejected = decision.requested
        elif decision.status == "approved":
            self.settled = True


def _flow_tools(turn: _Turn, pending: Decimal | None) -> list[BaseTool]:
    def accept_interview() -> str:
        """Start the score interview after a rejected request."""
        if pending is None and turn.rejected is None:
            return "No rejected request to reanalyse."
        turn.accepted = True
        return "Interview started."

    def decline_interview() -> str:
        """Record that the customer does not want the score interview."""
        turn.declined = True
        return "Interview declined."

    return [
        StructuredTool.from_function(accept_interview),
        StructuredTool.from_function(decline_interview),
    ]


def _reanalysis(service: CreditService, cpf: str, state: GraphState) -> dict[str, object]:
    pending = state["pending_limit"]
    score = state["interview"]["score"]
    decision = service.request_increase(cpf, pending)  # type: ignore[arg-type]
    if decision.status == "approved":
        text = (
            f"Com o seu novo score de {score}, reanalisei o pedido de "
            f"{format_brl(decision.requested or Decimal(0))}. {decision.message}"
        )
    elif decision.status == "rejected":
        text = (
            f"Com o seu novo score de {score}, reanalisei o pedido de "
            f"{format_brl(decision.requested or Decimal(0))}, mas o score ainda não permite "
            "esse limite. Posso ajudar com mais alguma coisa?"
        )
    else:
        text = decision.message
    return {
        "messages": [AIMessage(content=text)],
        "pending_limit": None,
        "interview": {},
        "active_agent": "triage",
    }


def make_credit_node(
    model: BaseChatModel, service: CreditService
) -> Callable[[GraphState], dict[str, object]]:
    def credit_node(state: GraphState) -> dict[str, object]:
        cpf = state.get("customer_cpf")
        if not cpf:
            return {"active_agent": "triage"}
        pending = state.get("pending_limit")
        if pending is not None and (state.get("interview") or {}).get("score") is not None:
            return _reanalysis(service, cpf, state)

        turn = _Turn()
        tools = [*build_credit_tools(service, cpf, turn.on_decision), *_flow_tools(turn, pending)]
        reply = run_tool_loop(
            model,
            CREDIT_PROMPT,
            state.get("messages", []),
            tools,
            stop_when=lambda: turn.accepted,
        )
        update: dict[str, object] = {}
        if reply is not None:
            update["messages"] = [AIMessage(content=reply.content)]
        if turn.accepted:
            update.update(
                active_agent="interview",
                interview={},
                pending_limit=turn.rejected if turn.rejected is not None else pending,
            )
        elif turn.rejected is not None:
            update.update(pending_limit=turn.rejected, active_agent="credit")
        elif turn.declined or turn.settled or pending is None:
            update.update(pending_limit=None, active_agent="triage")
        return update

    return credit_node
