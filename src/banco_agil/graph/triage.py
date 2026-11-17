import re
from collections.abc import Callable
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from pydantic import BaseModel

from banco_agil.domain.auth import (
    BirthLookup,
    authenticate,
    find_birth_date,
    parse_birth_date,
    register_failure,
)
from banco_agil.domain.cpf import find_cpf
from banco_agil.graph.state import GraphState

GREETING = "Olá! Eu sou o atendimento do Banco Ágil. Para começar, informe o seu CPF, por favor."
ASK_CPF = "Para seguir com o atendimento, preciso primeiro do seu CPF. Pode informar, por favor?"
ASK_CPF_VARIANTS = (
    ASK_CPF,
    "Antes de seguir, preciso confirmar a sua identidade. Qual é o seu CPF?",
    "Para liberar o atendimento, informe o seu CPF, por favor.",
)
ASK_BIRTH_DATE = "Obrigado. Agora informe a sua data de nascimento (DD/MM/AAAA)."
AUTH_RETRY = (
    "Não foi possível autenticar com os dados informados. "
    "Vamos tentar de novo: informe o seu CPF, por favor."
)
AUTH_RETRY_VARIANTS = (
    AUTH_RETRY,
    "Os dados ainda não conferem. Informe o seu CPF novamente, por favor, "
    "e depois a data de nascimento.",
)
CPF_FORMAT_HELP = (
    "Não consegui ler o CPF. Ele precisa ter 11 dígitos, com ou sem pontos e traço. "
    "Informe o seu CPF, por favor."
)
CPF_FORMAT_HELP_VARIANTS = (
    CPF_FORMAT_HELP,
    "O CPF informado está incompleto. Digite os 11 números, por exemplo 123.456.789-09.",
)
BIRTH_FORMAT_HELP = (
    "Não consegui ler a data de nascimento. Use DD/MM/AAAA ou AAAA-MM-DD. "
    "Informe a data novamente, por favor."
)
BIRTH_FORMAT_HELP_VARIANTS = (
    BIRTH_FORMAT_HELP,
    "A data de nascimento não está num formato que eu consiga ler. "
    "Digite no formato 17/05/1990, por favor.",
)
AUTH_LOCKED = (
    "Não foi possível autenticar o seu acesso e por isso vou encerrar o atendimento por aqui. "
    "Obrigado por procurar o Banco Ágil, e até a próxima!"
)
AUTH_OK = "Autenticação concluída. Como posso ajudar você hoje?"
SCOPE_HELP = (
    "Posso ajudar com o seu limite de crédito (consulta e pedido de aumento), "
    "com a atualização do seu score por uma entrevista rápida e com a cotação de moedas. "
    "Sobre o que você gostaria de falar?"
)
FAREWELL = "Atendimento encerrado. Obrigado por escolher o Banco Ágil!"

TRIAGE_PROMPT = (
    "You classify the latest customer message of a digital bank into one topic:\n"
    "- credit: asks about credit limit or wants a limit increase\n"
    "- interview: wants to update or recalculate the credit score\n"
    "- exchange: asks for a currency exchange rate\n"
    "- end: wants to finish the conversation\n"
    "- out_of_scope: anything else, including investment advice\n"
    "Answer only with the topic."
)

_AGENT_FOR_TOPIC = {"credit": "credit", "interview": "interview", "exchange": "exchange"}


class TriageDecision(BaseModel):
    topic: Literal["credit", "interview", "exchange", "end", "out_of_scope"]


def _last_human_text(messages: list[AnyMessage]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return message.content if isinstance(message.content, str) else ""
    return ""


def _pick(options: tuple[str, ...], index: int) -> str:
    return options[min(index, len(options) - 1)]


def _ask_cpf(state: GraphState) -> str:
    replies = sum(1 for m in state.get("messages", []) if isinstance(m, AIMessage))
    if replies == 0:
        return GREETING
    return ASK_CPF_VARIANTS[(replies - 1) % len(ASK_CPF_VARIANTS)]


def _reply(text: str, **update: object) -> dict[str, object]:
    return {"messages": [AIMessage(content=text)], **update}


def make_auth_node(lookup: BirthLookup) -> Callable[[GraphState], dict[str, object]]:
    def auth_node(state: GraphState) -> dict[str, object]:
        text = _last_human_text(state.get("messages", []))
        attempts = state.get("auth_attempts", 0)
        candidate = state.get("cpf_candidate")
        cpf_in_text = find_cpf(text)
        birth_in_text = find_birth_date(text)

        if candidate is None:
            if cpf_in_text is None:
                if _looks_like_cpf_attempt(text):
                    return _failure(
                        attempts, _pick(CPF_FORMAT_HELP_VARIANTS, attempts), keep_candidate=None
                    )
                return _reply(_ask_cpf(state))
            if birth_in_text is None:
                return _reply(ASK_BIRTH_DATE, cpf_candidate=cpf_in_text)
            cpf, birth = cpf_in_text, birth_in_text
        else:
            cpf = cpf_in_text or candidate
            birth = birth_in_text or text.strip()
            if parse_birth_date(birth) is None:
                return _failure(
                    attempts, _pick(BIRTH_FORMAT_HELP_VARIANTS, attempts), keep_candidate=cpf
                )

        outcome = authenticate(cpf, birth, lookup, attempts)
        if outcome.status == "authenticated":
            return _reply(
                AUTH_OK,
                phase="active",
                customer_cpf=outcome.cpf,
                cpf_candidate=None,
                auth_attempts=0,
                active_agent="triage",
            )
        return _failure(attempts, _pick(AUTH_RETRY_VARIANTS, attempts), keep_candidate=None)

    return auth_node


def _looks_like_cpf_attempt(text: str) -> bool:
    return bool(re.fullmatch(r"[\d.\-\s]+", text)) and any(ch.isdigit() for ch in text)


def _failure(attempts: int, retry_text: str, keep_candidate: str | None) -> dict[str, object]:
    outcome = register_failure(attempts)
    if outcome.status == "locked":
        return _reply(
            AUTH_LOCKED, phase="ended", auth_attempts=outcome.attempts, cpf_candidate=None
        )
    return _reply(retry_text, auth_attempts=outcome.attempts, cpf_candidate=keep_candidate)


def make_triage_node(model: BaseChatModel) -> Callable[[GraphState], dict[str, object]]:
    classifier = model.with_structured_output(TriageDecision)

    def triage_node(state: GraphState) -> dict[str, object]:
        if not state.get("customer_cpf"):
            return _reply(GREETING, phase="auth")
        recent = state.get("messages", [])[-6:]
        decision = classifier.invoke([SystemMessage(content=TRIAGE_PROMPT), *recent])
        topic = decision.topic if isinstance(decision, TriageDecision) else "out_of_scope"
        if topic in _AGENT_FOR_TOPIC:
            return {"active_agent": _AGENT_FOR_TOPIC[topic]}
        if topic == "end":
            return _reply(FAREWELL, phase="ended")
        return _reply(SCOPE_HELP, active_agent="triage")

    return triage_node
