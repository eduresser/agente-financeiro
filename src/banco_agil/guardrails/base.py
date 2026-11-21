from dataclasses import dataclass
from typing import Literal, Protocol

from banco_agil.domain.privacy import Known

BLOCKED_INPUT_REPLY = (
    "Não consegui processar essa mensagem. Pode reformular o que você precisa, por favor?"
)
BLOCKED_INPUT_REPLY_REPEAT = (
    "Não posso ajudar com esse tipo de pedido. Posso atender você com o limite de crédito, "
    "a atualização do score e a cotação de moedas."
)
BLOCKED_INPUT_PLACEHOLDER = "Mensagem não enviada: bloqueada pelo filtro de segurança."
SAFE_OUTPUT_REPLY = (
    "Desculpe, não posso responder isso. Posso ajudar com o seu limite de crédito, "
    "a atualização do seu score e a cotação de moedas."
)
CLOSING_REPLY = (
    "Por segurança, vou encerrar o atendimento por aqui. Obrigado por procurar o Banco Ágil!"
)

Direction = Literal["input", "output"]


@dataclass(frozen=True)
class GuardContext:
    customer_cpf: str | None = None
    thread_id: str = "unknown"
    user_text: str = ""
    known: Known = Known()  # noqa: B008


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    reason: str | None = None


ALLOWED = GuardResult(True)


class Guardrail(Protocol):
    def check_input(self, text: str, context: GuardContext) -> GuardResult: ...

    def check_output(self, text: str, context: GuardContext) -> GuardResult: ...


class Judge(Protocol):
    def is_safe(self, text: str, direction: Direction) -> bool: ...
