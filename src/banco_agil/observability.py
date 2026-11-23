from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage, HumanMessage

from banco_agil.config import Settings
from banco_agil.domain.privacy import redact_sensitive
from banco_agil.logging_utils import get_logger

logger = get_logger(__name__)

REDACTED = "[redacted]"
_CUSTOMER_ROLES = {"human", "user"}


def redact(data: Any) -> Any:  # noqa: ANN401
    if isinstance(data, HumanMessage):
        return HumanMessage(content=REDACTED, id=data.id)
    if isinstance(data, BaseMessage):
        content = (
            redact_sensitive(data.content) if isinstance(data.content, str) else data.content
        )
        return data.model_copy(update={"content": content})
    if isinstance(data, dict):
        if data.get("type") in _CUSTOMER_ROLES or data.get("role") in _CUSTOMER_ROLES:
            return {**data, "content": REDACTED}
        return {key: redact(item) for key, item in data.items()}
    if isinstance(data, list | tuple):
        return [redact(item) for item in data]
    if isinstance(data, str):
        return redact_sensitive(data)
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
