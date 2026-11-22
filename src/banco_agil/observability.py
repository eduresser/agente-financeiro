from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage, HumanMessage

from banco_agil.config import Settings
from banco_agil.domain.privacy import redact_sensitive
from banco_agil.logging_utils import get_logger

logger = get_logger(__name__)

REDACTED = "[redacted]"
_CUSTOMER_ROLES = {"human", "user"}


def redact(value: Any) -> Any:  # noqa: ANN401
    if isinstance(value, HumanMessage):
        return HumanMessage(content=REDACTED, id=value.id)
    if isinstance(value, BaseMessage):
        content = (
            redact_sensitive(value.content) if isinstance(value.content, str) else value.content
        )
        return value.model_copy(update={"content": content})
    if isinstance(value, dict):
        if value.get("type") in _CUSTOMER_ROLES or value.get("role") in _CUSTOMER_ROLES:
            return {**value, "content": REDACTED}
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive(value)
    return value


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
