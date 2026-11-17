import pytest

from banco_agil.config import ConfigError, env_var_names, load_settings
from banco_agil.llm import build_chat_model, build_judge_model


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.TempPathFactory) -> None:
    monkeypatch.chdir(tmp_path)
    for name in env_var_names():
        monkeypatch.delenv(name, raising=False)


def test_missing_required_variables_are_listed_without_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAT_MODEL_BASE_URL", "http://secret-host.local")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    message = str(exc.value)
    assert "CHAT_MODEL" in message
    assert "CHAT_MODEL_API_KEY" in message
    assert "secret-host.local" not in message


def test_env_example_lists_every_variable_the_app_reads() -> None:
    from pathlib import Path

    example = Path(__file__).parent.parent / ".env.example"
    declared = {line.split("=", 1)[0] for line in example.read_text().splitlines() if "=" in line}
    assert set(env_var_names()) <= declared


def test_model_factory_passes_base_url_only_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAT_MODEL", "provider/some-model")
    monkeypatch.setenv("CHAT_MODEL_API_KEY", "k-123456789")
    monkeypatch.setenv("JUDGE_CHAT_MODEL", "provider/judge-model")
    monkeypatch.setenv("JUDGE_CHAT_MODEL_API_KEY", "j-123456789")
    without = build_chat_model(load_settings())
    assert without.api_base in (None, "")  # type: ignore[attr-defined]
    monkeypatch.setenv("CHAT_MODEL_BASE_URL", "http://proxy.local/v1")
    with_url = build_chat_model(load_settings())
    assert with_url.api_base == "http://proxy.local/v1"  # type: ignore[attr-defined]


def test_empty_optional_variables_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_MODEL", "provider/some-model")
    monkeypatch.setenv("CHAT_MODEL_API_KEY", "k-123456789")
    monkeypatch.setenv("JUDGE_CHAT_MODEL", "provider/judge-model")
    monkeypatch.setenv("JUDGE_CHAT_MODEL_API_KEY", "j-123456789")
    monkeypatch.setenv("EXCHANGE_API_BASE_URL", "")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    settings = load_settings()
    assert settings.exchange_api_base_url == "https://economia.awesomeapi.com.br"
    assert settings.observability_enabled is False


def test_empty_required_variable_is_reported_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_MODEL", "")
    monkeypatch.setenv("CHAT_MODEL_API_KEY", "")
    with pytest.raises(ConfigError, match="CHAT_MODEL_API_KEY"):
        load_settings()


def test_session_timeout_defaults_to_300_and_zero_disables_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAT_MODEL", "m")
    monkeypatch.setenv("CHAT_MODEL_API_KEY", "k")
    monkeypatch.setenv("JUDGE_CHAT_MODEL", "j")
    monkeypatch.setenv("JUDGE_CHAT_MODEL_API_KEY", "j")
    assert load_settings().session_timeout_seconds == 300
    monkeypatch.setenv("SESSION_TIMEOUT_SECONDS", "0")
    assert load_settings().session_timeout_seconds == 0


def test_judge_model_uses_its_own_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_MODEL", "provider/chat-model")
    monkeypatch.setenv("CHAT_MODEL_API_KEY", "k-123456789")
    monkeypatch.setenv("CHAT_MODEL_BASE_URL", "http://chat.local/v1")
    monkeypatch.setenv("JUDGE_CHAT_MODEL", "other/judge-model")
    monkeypatch.setenv("JUDGE_CHAT_MODEL_API_KEY", "j-123456789")
    settings = load_settings()
    judge = build_judge_model(settings)
    assert judge.model == "other/judge-model"  # type: ignore[attr-defined]
    assert judge.api_base in (None, "")  # type: ignore[attr-defined]
    assert build_chat_model(settings).model == "provider/chat-model"  # type: ignore[attr-defined]


def test_missing_judge_variables_are_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_MODEL", "m")
    monkeypatch.setenv("CHAT_MODEL_API_KEY", "k")
    with pytest.raises(ConfigError, match="JUDGE_CHAT_MODEL"):
        load_settings()
