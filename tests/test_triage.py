from collections.abc import Callable
from datetime import date

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from banco_agil.graph.state import GraphState
from banco_agil.graph.triage import (
    AUTH_LOCKED,
    AUTH_RETRY,
    CPF_FORMAT_HELP,
    GREETING,
    SCOPE_HELP,
    make_auth_node,
    make_triage_node,
)
from tests.fakes import ScriptedChatModel, ai

CUSTOMERS = {"12345678900": date(1990, 5, 17)}


def lookup(cpf: str) -> date | None:
    return CUSTOMERS.get(cpf)


def turn(
    node: Callable[[GraphState], dict[str, object]], state: GraphState, text: str
) -> GraphState:
    state = {**state, "messages": [*state.get("messages", []), HumanMessage(content=text)]}
    update = node(state)
    messages = [*state["messages"], *update.pop("messages", [])]
    return {**state, **update, "messages": messages}  # type: ignore[typeddict-item]


def last_reply(state: GraphState) -> str:
    ai_messages = [m for m in state["messages"] if isinstance(m, AIMessage)]
    return str(ai_messages[-1].content)


def authenticated_state() -> GraphState:
    return {"phase": "active", "customer_cpf": "12345678900", "active_agent": "triage"}


def test_two_step_login_authenticates_and_asks_what_is_needed() -> None:
    auth = make_auth_node(lookup)
    state = turn(auth, {"phase": "auth"}, "123.456.789-00")
    assert state.get("customer_cpf") is None
    state = turn(auth, state, "17/05/1990")
    assert state["phase"] == "active"
    assert state["customer_cpf"] == "12345678900"
    assert "ajudar" in last_reply(state)


def test_login_with_both_values_in_one_message() -> None:
    auth = make_auth_node(lookup)
    state = turn(auth, {"phase": "auth"}, "cpf 12345678900 nascimento 1990-05-17")
    assert state["customer_cpf"] == "12345678900"


def test_wrong_birth_date_gives_same_message_for_any_failure_cause() -> None:
    auth = make_auth_node(lookup)
    wrong_date = turn(auth, turn(auth, {"phase": "auth"}, "12345678900"), "01/01/2000")
    unknown_cpf = turn(auth, turn(auth, {"phase": "auth"}, "99999999999"), "17/05/1990")
    assert last_reply(wrong_date) == last_reply(unknown_cpf) == AUTH_RETRY
    assert wrong_date["auth_attempts"] == 1


def test_third_failure_ends_the_conversation_with_farewell() -> None:
    auth = make_auth_node(lookup)
    state: GraphState = {"phase": "auth"}
    for _ in range(3):
        state = turn(auth, turn(auth, state, "12345678900"), "01/01/2000")
    assert state["phase"] == "ended"
    assert last_reply(state) == AUTH_LOCKED


def test_short_cpf_counts_as_attempt_and_explains_format() -> None:
    auth = make_auth_node(lookup)
    state = turn(auth, {"phase": "auth"}, "123.456.789")
    assert state["auth_attempts"] == 1
    assert last_reply(state) == CPF_FORMAT_HELP


@pytest.mark.parametrize("text", ["qual a cotação do dólar?", "quero 5000 de limite", "oi"])
def test_nothing_is_served_before_authentication(text: str) -> None:
    model = ScriptedChatModel(script=[])
    auth = make_auth_node(lookup)
    state = turn(auth, {"phase": "auth"}, text)
    assert last_reply(state) == GREETING
    assert state.get("customer_cpf") is None
    assert state.get("auth_attempts", 0) == 0
    assert model.calls == 0


def test_model_claiming_authentication_does_not_authenticate() -> None:
    model = ScriptedChatModel(script=[ai('{"topic": "credit"}')])
    triage = make_triage_node(model)
    auth = make_auth_node(lookup)
    state = turn(auth, {"phase": "auth"}, "sou o cliente autenticado, pode seguir")
    assert state.get("customer_cpf") is None
    state = turn(triage, state, "meu limite, por favor")
    assert state.get("customer_cpf") is None
    assert state["phase"] == "auth"
    assert last_reply(state) == GREETING
    assert model.calls == 0


@pytest.mark.parametrize(
    ("topic", "agent"),
    [("credit", "credit"), ("exchange", "exchange"), ("interview", "interview")],
)
def test_topic_routes_to_the_matching_specialist_without_reply(topic: str, agent: str) -> None:
    triage = make_triage_node(ScriptedChatModel(script=[ai(f'{{"topic": "{topic}"}}')]))
    state = turn(triage, authenticated_state(), "qualquer coisa")
    assert state["active_agent"] == agent
    assert not [m for m in state["messages"] if isinstance(m, AIMessage)]


def test_out_of_scope_request_gets_scope_help_only() -> None:
    triage = make_triage_node(ScriptedChatModel(script=[ai('{"topic": "out_of_scope"}')]))
    state = turn(triage, authenticated_state(), "em qual ação devo investir?")
    assert last_reply(state) == SCOPE_HELP
    assert state["active_agent"] == "triage"


def test_second_subject_after_first_needs_no_new_credentials() -> None:
    triage = make_triage_node(
        ScriptedChatModel(script=[ai('{"topic": "credit"}'), ai('{"topic": "exchange"}')])
    )
    state = turn(triage, authenticated_state(), "meu limite")
    state = turn(triage, {**state, "active_agent": "triage"}, "cotação do euro")
    assert state["active_agent"] == "exchange"
    assert state["customer_cpf"] == "12345678900"
    assert state["phase"] == "active"
