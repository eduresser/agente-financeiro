from langchain_core.language_models.chat_models import BaseChatModel
from langchain_litellm import ChatLiteLLM

from banco_agil.config import Settings, get_settings


def build_chat_model(settings: Settings | None = None, **overrides: object) -> BaseChatModel:
    settings = settings or get_settings()
    kwargs: dict[str, object] = {
        "model": settings.chat_model,
        "api_key": settings.chat_model_api_key,
        "request_timeout": 30,
        "max_retries": 1,
    }
    if settings.chat_model_base_url:
        kwargs["api_base"] = settings.chat_model_base_url
    kwargs.update(overrides)
    return ChatLiteLLM(**kwargs)
