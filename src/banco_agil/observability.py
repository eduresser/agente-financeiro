from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, cast

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage

from banco_agil.config import Settings
from banco_agil.domain.privacy import Known, redact_sensitive
from banco_agil.graph.state import GraphState, known_from_state
from banco_agil.logging_utils import get_logger

logger = get_logger(__name__)

_known_in_turn: ContextVar[Known] = ContextVar("known_in_turn", default=Known())  # noqa: B039
_STATE_KEYS = {"customer_cpf", "birth_candidate"}


@contextmanager
def known_in_turn(known: Known) -> Iterator[None]:
    token = _known_in_turn.set(known)
    try:
        yield
    finally:
        _known_in_turn.reset(token)


def redact(data: Any) -> Any:  # noqa: ANN401
    return _redact(data, _known_in_turn.get())


def _redact(data: Any, known: Known) -> Any:  # noqa: ANN401
    if isinstance(data, BaseMessage):
        if not isinstance(data.content, str):
            return data
        return data.model_copy(update={"content": redact_sensitive(data.content, known)})
    if isinstance(data, dict):
        if _STATE_KEYS & data.keys():
            known = known_from_state(cast("GraphState", data))
        return {key: _redact(item, known) for key, item in data.items()}
    if isinstance(data, list | tuple):
        return [_redact(item, known) for item in data]
    if isinstance(data, str):
        return redact_sensitive(data, known)
    return data


def build_callbacks(settings: Settings) -> list[BaseCallbackHandler]:
    if not settings.observability_enabled:
        return []
    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        options: dict[str, Any] = {
            "public_key": settings.langfuse_public_key,
            "secret_key": settings.langfuse_secret_key,
            "mask": redact,
        }
        if settings.langfuse_host:
            options["host"] = settings.langfuse_host
        Langfuse(**options)
        return [CallbackHandler(public_key=settings.langfuse_public_key)]
    except Exception as exc:
        logger.warning("observability_disabled error=%s", type(exc).__name__)
        return []
