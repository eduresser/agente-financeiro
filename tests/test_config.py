import pytest

from banco_agil.config import ConfigError, env_var_names, load_settings
from banco_agil.llm import build_chat_model


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


def test_api_key_value_never_appears_in_error_when_other_variable_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CHAT_MODEL_API_KEY", "sk-super-secret-value")
    with pytest.raises(ConfigError) as exc:
        load_settings()
    assert "sk-super-secret-value" not in str(exc.value)
    assert "CHAT_MODEL" in str(exc.value)


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
    without = build_chat_model(load_settings())
    assert without.api_base in (None, "")  # type: ignore[attr-defined]
    monkeypatch.setenv("CHAT_MODEL_BASE_URL", "http://proxy.local/v1")
    with_url = build_chat_model(load_settings())
    assert with_url.api_base == "http://proxy.local/v1"  # type: ignore[attr-defined]
