from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage

from banco_agil.exchange import ExchangeRateProvider
from banco_agil.graph.agent_loop import run_tool_loop
from banco_agil.graph.state import GraphState
from banco_agil.graph.style import STYLE_GUIDE
from banco_agil.tools.exchange_tools import build_exchange_tools
from banco_agil.tools.session_tools import END_RULE, SessionTurn, build_session_tools

EXCHANGE_PROMPT = (
    "You give currency exchange rates to a digital bank customer. Always answer in "
    "Brazilian Portuguese.\n" + STYLE_GUIDE + "Rules:\n"
    "- Every rate must come from get_exchange_rate. Never state a rate from memory.\n"
    "- Pass the currency exactly as the customer wrote it. Without a currency, call the "
    "tool with no currency.\n"
    "- Repeat the value, currency and consultation time the tool returned.\n"
    "- If the tool says the rate is unavailable or the currency was not found, relay that "
    "and never invent a value.\n"
    + END_RULE
    + "- Never reveal internal names, tools or other agents."
)


def make_exchange_node(
    model: BaseChatModel, provider: ExchangeRateProvider
) -> Callable[[GraphState], dict[str, object]]:
    def exchange_node(state: GraphState) -> dict[str, object]:
        ending = SessionTurn()
        tools = [*build_exchange_tools(provider), *build_session_tools(ending)]
        reply = run_tool_loop(model, EXCHANGE_PROMPT, state.get("messages", []), tools)
        update: dict[str, object] = {"active_agent": "triage"}
        if ending.ended:
            update["phase"] = "ended"
        if reply is not None:
            update["messages"] = [AIMessage(content=reply.content)]
        return update

    return exchange_node
