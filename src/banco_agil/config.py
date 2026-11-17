from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(Exception):
    pass


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", case_sensitive=False, env_ignore_empty=True
    )

    chat_model: str = Field(min_length=1)
    chat_model_api_key: str = Field(min_length=1, repr=False)
    chat_model_base_url: str | None = None
    judge_chat_model: str = Field(min_length=1)
    judge_chat_model_api_key: str = Field(min_length=1, repr=False)
    judge_chat_model_base_url: str | None = None
    exchange_api_base_url: str = "https://economia.awesomeapi.com.br"
    session_timeout_seconds: int = Field(default=300, ge=0)
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = Field(default=None, repr=False)
    langfuse_host: str | None = None

    @property
    def observability_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


def env_var_names() -> list[str]:
    return [name.upper() for name in Settings.model_fields]


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        names = sorted({str(err["loc"][0]).upper() for err in exc.errors() if err["loc"]})
        raise ConfigError(f"Missing or invalid environment variables: {', '.join(names)}") from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
