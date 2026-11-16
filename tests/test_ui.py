from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from banco_agil.service import Reply

APP = Path(__file__).parent.parent / "src" / "banco_agil" / "ui" / "streamlit_app.py"


class StubService:
    def __init__(self) -> None:
        self.threads: dict[str, list[tuple[str, str]]] = {}
        self.ended: set[str] = set()

    def send(self, thread_id: str, text: str) -> Reply:
        history = self.threads.setdefault(thread_id, [])
        history += [("user", text), ("assistant", "Atendimento encerrado, até logo!")]
        self.ended.add(thread_id)
        return Reply("Atendimento encerrado, até logo!", ended=True)

    def history(self, thread_id: str) -> list[tuple[str, str]]:
        return list(self.threads.get(thread_id, []))

    def is_ended(self, thread_id: str) -> bool:
        return thread_id in self.ended


@pytest.fixture
def stub(monkeypatch: pytest.MonkeyPatch) -> StubService:
    service = StubService()
    monkeypatch.setattr("banco_agil.service.create_service", lambda *a, **k: service)
    st.cache_resource.clear()
    return service


def test_ended_conversation_disables_input_and_new_conversation_starts_clean(
    stub: StubService,
) -> None:
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not app.exception
    assert app.chat_input[0].disabled is False
    first_thread = app.session_state["thread_id"]

    app.chat_input[0].set_value("quero encerrar").run()
    assert app.chat_input[0].disabled is True
    assert [b.label for b in app.button] == ["Nova conversa"]
    assert "quero encerrar" in [m.markdown[0].value for m in app.chat_message if m.markdown]

    app.button[0].click().run()
    assert app.session_state["thread_id"] != first_thread
    assert app.chat_input[0].disabled is False
    assert len(app.chat_message) == 0
    assert stub.history(app.session_state["thread_id"]) == []


def test_missing_configuration_shows_variable_names_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from banco_agil.config import ConfigError

    def failing(*args: object, **kwargs: object) -> None:
        raise ConfigError("Missing or invalid environment variables: CHAT_MODEL")

    monkeypatch.setattr("banco_agil.service.create_service", failing)
    st.cache_resource.clear()
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not app.exception
    assert "CHAT_MODEL" in app.error[0].value
    assert len(app.chat_input) == 0
