from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from banco_agil.graph.triage import GREETING
from banco_agil.service import Reply
from banco_agil.ui.streamlit_app import idle_expired

APP = Path(__file__).parent.parent / "src" / "banco_agil" / "ui" / "streamlit_app.py"


class StubService:
    def __init__(self) -> None:
        self.threads: dict[str, list[tuple[str, str]]] = {}
        self.ended: set[str] = set()
        self.idle_timeout = 0

    def start(self, thread_id: str) -> None:
        self.threads.setdefault(thread_id, [("assistant", GREETING)])

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
    assert [m.markdown[0].value for m in app.chat_message] == [GREETING]
    assert stub.history(app.session_state["thread_id"]) == [("assistant", GREETING)]


def test_new_conversation_opens_with_the_greeting(stub: StubService) -> None:
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not app.exception
    assert [m.markdown[0].value for m in app.chat_message] == [GREETING]
    assert app.chat_input[0].disabled is False


@pytest.mark.parametrize(
    ("last", "timeout", "now", "expected"),
    [
        (None, 300, 10_000.0, False),
        (100.0, 0, 10_000.0, False),
        (100.0, 300, 399.9, False),
        (100.0, 300, 400.0, True),
    ],
)
def test_idle_expiry_boundaries(
    last: float | None, timeout: int, now: float, expected: bool
) -> None:
    assert idle_expired(last, timeout, now) is expected


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
