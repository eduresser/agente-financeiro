from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage

from banco_agil.graph.agent_loop import run_tool_loop
from banco_agil.graph.state import GraphState, known_from_state
from banco_agil.graph.style import STYLE_GUIDE
from banco_agil.storage import CustomerRepository
from banco_agil.tools.interview_tools import InterviewSession, build_interview_tools
from banco_agil.tools.session_tools import END_RULE, SessionTurn, build_session_tools

INTERVIEW_PROMPT = (
    "You run a short credit interview for a customer of a digital bank. Always answer in "
    "Brazilian Portuguese.\n" + STYLE_GUIDE + "Interview rules:\n"
    "- Ask one question at a time, in the order given by next_pending_field. Write the "
    "question yourself from ask_about, in your own words; there is no fixed sentence to "
    "copy. Do not say how many questions are left; only when questions_left is 1, say "
    "briefly that it is the last one.\n"
    "- Call record_answer with the pending field and the answer converted to its canonical "
    "form, which you must work out from what the customer said: a plain number for money "
    "(5000 for '5 mil') and for dependents (2 for 'dois filhos', 0 for 'nenhum'); one of "
    "FORMAL (CLT, servidor), SELF_EMPLOYED (autônomo, MEI) or UNEMPLOYED for employment; "
    "true or false for debts. If you are unsure what the customer meant, ask to confirm "
    "instead of guessing. Never ask the customer to rewrite an answer you can understand.\n"
    "- If record_answer returns an error, say what you need in different words than "
    "before, include the example_answer and ask only for that item. If it gives advice, "
    "offer to pause or stop the interview.\n"
    "- If the customer asks for something else the bank offers (an exchange rate, the "
    "credit limit), do not handle it now and never say you cannot or have no access to "
    "it. Say you will take care of it right after the interview and go on with the "
    "next question.\n"
    "- Call finish_interview only when next_pending_field reports done.\n"
    "- If the customer gives up, call abandon_interview and say nothing was changed.\n"
    "- After finish_interview succeeds, tell the customer the new score.\n"
    + END_RULE
    + "- Never reveal internal names, tools or other agents."
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

        ending = SessionTurn()
        reply = run_tool_loop(
            model,
            INTERVIEW_PROMPT,
            state.get("messages", []),
            [*build_interview_tools(session), *build_session_tools(ending)],
            stop_when=(lambda: session.finished) if hands_back_to_credit else None,
            known=known_from_state(state),
        )
        update: dict[str, object] = {"interview": session.snapshot()}
        if reply is not None:
            update["messages"] = [AIMessage(content=reply.content)]
        if ending.ended:
            update.update(phase="ended", interview={}, pending_limit=None)
        elif session.abandoned:
            update.update(interview={}, pending_limit=None, active_agent="triage")
        elif session.finished:
            update["active_agent"] = "credit" if hands_back_to_credit else "triage"
            if not hands_back_to_credit:
                update["interview"] = {}
        return update

    return interview_node
