from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage

from banco_agil.domain.auth import (
    BIRTH_DIGITS,
    calendar_dates,
    digit_spans,
    extract_credentials,
    split_joined,
)

CPF_PLACEHOLDER = "[CPF]"
DATE_PLACEHOLDER = "[DATA]"
BLOCKED_BY_GUARD = "blocked_by_guard"


@dataclass(frozen=True)
class Known:
    cpf: str | None = None
    birth: date | None = None
    logged_in: bool = False


def _sensitive_values(text: str, known: Known) -> tuple[set[str], set[date]]:
    cpfs = {known.cpf} if known.cpf else set()
    births = {known.birth} if known.birth else set()
    if not known.logged_in:
        found = extract_credentials(text)
        if found.cpf:
            cpfs.add(found.cpf)
        if found.birth:
            births.add(found.birth)
    return cpfs, births


def _placeholder_for(piece: str, cpfs: set[str], births: set[date]) -> str | None:
    if piece in cpfs:
        return CPF_PLACEHOLDER
    if len(piece) == BIRTH_DIGITS and any(d in births for d in calendar_dates(piece)):
        return DATE_PLACEHOLDER
    return None


def redact_sensitive(text: str, known: Known = Known()) -> str:  # noqa: B008
    cpfs, births = _sensitive_values(text, known)
    if not cpfs and not births:
        return text
    for group in reversed(digit_spans(text)):
        pieces = split_joined(group.digits)
        marks = [_placeholder_for(piece, cpfs, births) for piece in pieces]
        if not any(marks):
            continue
        replacement = " ".join(mark or piece for mark, piece in zip(marks, pieces, strict=True))
        text = text[: group.start] + replacement + text[group.end :]
    return text


def is_blocked_message(message: AnyMessage) -> bool:
    return bool(message.additional_kwargs.get(BLOCKED_BY_GUARD))


def messages_for_model(messages: Sequence[AnyMessage], known: Known = Known()) -> list[AnyMessage]:  # noqa: B008
    view: list[AnyMessage] = []
    for message in messages:
        if is_blocked_message(message):
            continue
        if isinstance(message, HumanMessage | AIMessage) and isinstance(message.content, str):
            clean = redact_sensitive(message.content, known)
            message = message.model_copy(update={"content": clean})
        view.append(message)
    return view
