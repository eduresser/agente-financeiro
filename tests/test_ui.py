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
        self.discarded: list[str] = []

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

    def discard(self, thread_id: str) -> None:
        self.discarded.append(thread_id)
        self.threads.pop(thread_id, None)


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
    assert [b.label for b in app.button] == ["", ""]
    assert [i.value for i in app.info] == ["Atendimento encerrado."]
    assert "quero encerrar" in [m.markdown[0].value for m in app.chat_message if m.markdown]

    app.button[0].click().run()
    assert app.session_state["thread_id"] != first_thread
    assert app.chat_input[0].disabled is False
    assert [m.markdown[0].value for m in app.chat_message] == [GREETING]
    assert stub.history(app.session_state["thread_id"]) == [("assistant", GREETING)]


class EchoService(StubService):
    def __init__(self, fail: bool = False) -> None:
        super().__init__()
        self.fail = fail
        self.seen_pending: object = None

    def send(self, thread_id: str, text: str) -> Reply:
        self.seen_pending = st.session_state.get("pending_message")
        if self.fail:
            return Reply("Tive um problema técnico agora.", failed=True)
        history = self.threads.setdefault(thread_id, [])
        history += [("user", text), ("assistant", "Autenticado.")]
        return Reply("Autenticado.")


def use(monkeypatch: pytest.MonkeyPatch, service: StubService) -> None:
    monkeypatch.setattr("banco_agil.service.create_service", lambda *a, **k: service)
    st.cache_resource.clear()


def test_screen_shows_the_conversation_exactly_as_the_service_stores_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EchoService()
    use(monkeypatch, service)
    app = AppTest.from_file(str(APP), default_timeout=10).run()

    app.chat_input[0].set_value("meu cpf é 111.444.777-35").run()

    shown = [m.markdown[0].value for m in app.chat_message if m.markdown]
    assert shown == [GREETING, "meu cpf é 111.444.777-35", "Autenticado."]


def test_input_is_disabled_while_the_reply_is_being_processed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = EchoService()
    use(monkeypatch, service)
    disabled_per_render: list[bool] = []
    real_chat_input = st.chat_input

    def spy(*args: object, **kwargs: object) -> object:
        disabled_per_render.append(bool(kwargs.get("disabled")))
        return real_chat_input(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(st, "chat_input", spy)
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    disabled_per_render.clear()

    app.chat_input[0].set_value("quero meu limite").run()

    assert disabled_per_render == [False, True, False]
    assert service.seen_pending == "quero meu limite"
    assert app.chat_input[0].disabled is False
    assert app.session_state["pending_message"] is None


def test_input_gets_its_focus_back_once_after_the_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    use(monkeypatch, EchoService())
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not app.get("html")

    app.chat_input[0].set_value("quero meu limite").run()
    assert "stChatInputTextArea" in app.get("html")[0].proto.body

    app.run()
    assert not app.get("html")


def test_a_failed_turn_keeps_the_typed_message_and_shows_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, EchoService(fail=True))
    app = AppTest.from_file(str(APP), default_timeout=10).run()

    app.chat_input[0].set_value("meu limite?").run()

    shown = [m.markdown[0].value for m in app.chat_message if m.markdown]
    assert shown == [GREETING, "meu limite?", "Tive um problema técnico agora."]


def test_new_conversation_discards_the_previous_one(monkeypatch: pytest.MonkeyPatch) -> None:
    service = EchoService()
    use(monkeypatch, service)
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    first = app.session_state["thread_id"]
    app.chat_input[0].set_value("oi").run()

    app.button[0].click().run()

    assert service.discarded == [first]
    assert app.session_state["thread_id"] != first


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


def test_sidebar_new_conversation_resets_an_ongoing_chat(stub: StubService) -> None:
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    first_thread = app.session_state["thread_id"]
    app.chat_input[0].set_value("olá").run()
    assert app.chat_input[0].disabled is True

    app.button[0].click().run()
    assert app.session_state["thread_id"] != first_thread
    assert [m.markdown[0].value for m in app.chat_message] == [GREETING]


def test_sidebar_lists_seed_customers_and_saved_data(
    stub: StubService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from banco_agil.seed import bootstrap

    bootstrap(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    app = AppTest.from_file(str(APP), default_timeout=10).run()
    assert not app.exception
    app.button[1].click().run()
    roster = app.dataframe[0].value
    assert "11144477735" in roster["CPF"].tolist()
    assert "17/05/1990" in roster["Nascimento"].tolist()
