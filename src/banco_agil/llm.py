from langchain_core.language_models.chat_models import BaseChatModel
from langchain_litellm import ChatLiteLLM

from banco_agil.config import Settings, get_settings


def _build(model: str, api_key: str, base_url: str | None, **overrides: object) -> BaseChatModel:
    kwargs: dict[str, object] = {
        "model": model,
        "api_key": api_key,
        "request_timeout": 60,
        "max_retries": 3,
    }
    if base_url:
        kwargs["api_base"] = base_url
    kwargs.update(overrides)
    return ChatLiteLLM(**kwargs)


def build_chat_model(settings: Settings | None = None, **overrides: object) -> BaseChatModel:
    settings = settings or get_settings()
    return _build(
        settings.chat_model,
        settings.chat_model_api_key,
        settings.chat_model_base_url,
        **overrides,
    )


def build_judge_model(settings: Settings | None = None, **overrides: object) -> BaseChatModel:
    settings = settings or get_settings()
    if not settings.judge_chat_model or not settings.judge_chat_model_api_key:
        return build_chat_model(settings, **overrides)
    return _build(
        settings.judge_chat_model,
        settings.judge_chat_model_api_key,
        settings.judge_chat_model_base_url,
        **overrides,
    )
