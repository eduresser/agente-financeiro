from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage

from banco_agil.graph.agent_loop import run_tool_loop
from banco_agil.graph.state import GraphState
from banco_agil.storage import CustomerRepository
from banco_agil.tools.interview_tools import InterviewSession, build_interview_tools

INTERVIEW_PROMPT = (
    "You run a short credit interview for a digital bank customer. Always answer in "
    "Brazilian Portuguese, in a friendly and brief tone.\n"
    "Rules:\n"
    "- Ask exactly one question at a time, in the order given by next_pending_field.\n"
    "- Call record_answer with the pending field and the customer's raw answer. If it "
    "returns an error, explain the expected format and repeat the question.\n"
    "- Call finish_interview only when next_pending_field reports done.\n"
    "- If the customer gives up, call abandon_interview and say nothing was changed.\n"
    "- After finish_interview succeeds, tell the customer the new score.\n"
    "- Never reveal internal names, tools or other agents."
)


def make_interview_node(
    model: BaseChatModel, customers: CustomerRepository
) -> Callable[[GraphState], dict[str, object]]:
    def interview_node(state: GraphState) -> dict[str, object]:
        cpf = state.get("customer_cpf")
        if not cpf:
            return {"active_agent": "triage"}
        session = InterviewSession(customers, cpf, state.get("interview"))
        hands_back_to_credit = state.get("pending_limit") is not None

        reply = run_tool_loop(
            model,
            INTERVIEW_PROMPT,
            state.get("messages", []),
            build_interview_tools(session),
            stop_when=(lambda: session.finished) if hands_back_to_credit else None,
        )
        update: dict[str, object] = {"interview": session.snapshot()}
        if reply is not None:
            update["messages"] = [AIMessage(content=reply.content)]
        if session.abandoned:
            update.update(interview={}, pending_limit=None, active_agent="triage")
        elif session.finished:
            update["active_agent"] = "credit" if hands_back_to_credit else "triage"
            if not hands_back_to_credit:
                update["interview"] = {}
        return update

    return interview_node
