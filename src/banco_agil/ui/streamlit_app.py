import time
import uuid

import streamlit as st

from banco_agil.config import ConfigError
from banco_agil.seed.data import CUSTOMERS_FILE, CUSTOMERS_ROWS, LIMIT_REQUESTS_FILE
from banco_agil.service import ChatService, create_service
from banco_agil.storage import StorageError, default_data_dir
from banco_agil.storage.csv_store import read_rows

TITLE = "Banco Ágil"
INPUT_PLACEHOLDER = "Digite sua mensagem"
ENDED_NOTICE = "Atendimento encerrado."
NEW_CONVERSATION = "Nova conversa"
GUIDE_LABEL = "Roteiro de teste"
IDLE_CHECK_SECONDS = 5
DATA_ERROR = (
    "Não foi possível preparar os dados do atendimento. Verifique as permissões da pasta de dados."
)
AVATARS = {"user": "🙂", "assistant": "🏦"}
TOPBAR_CSS = """
<style>
.st-key-topbar {
    position: fixed;
    top: 0.5rem;
    left: 1rem;
    width: auto;
    z-index: 1000000;
}
</style>
"""
CAPTION = "Atendimento digital · ambiente de demonstração"
SCENARIOS = [
    ("Aumento aprovado", "Ana: peça limite de R$ 10.000 (score 650)"),
    ("Aumento rejeitado e entrevista", "Bruno: peça R$ 8.000, aceite a entrevista e responda"),
    ("Cotação de moeda", "Qualquer cliente: pergunte a cotação do dólar"),
    ("Falha de autenticação", "Informe dados errados 3 vezes seguidas"),
    ("Encerrar", "Diga a qualquer momento que quer encerrar"),
]


@st.cache_resource
def get_service() -> ChatService:
    return create_service()


def new_thread_id() -> str:
    return uuid.uuid4().hex


def idle_expired(last_activity: float | None, timeout: int, now: float) -> bool:
    return last_activity is not None and timeout > 0 and now - last_activity >= timeout


def watch_idle(service: ChatService, thread_id: str) -> None:
    @st.fragment(run_every=IDLE_CHECK_SECONDS)
    def check() -> None:
        last = st.session_state.get("last_activity")
        if service.is_ended(thread_id):
            return
        if idle_expired(last, service.idle_timeout, time.monotonic()):
            service.close_for_timeout(thread_id)
            st.rerun(scope="app")

    check()


def format_birth_date(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}/{month}/{year}"


def start_new_conversation() -> None:
    previous = st.session_state.get("thread_id")
    if previous:
        get_service().discard(previous)
    st.session_state.thread_id = new_thread_id()
    for key in ("last_activity", "pending_message", "failure"):
        st.session_state.pop(key, None)


@st.dialog("Roteiro de teste", width="large")
def show_test_guide() -> None:
    st.caption("Clientes fictícios para autenticação (CPF e data de nascimento).")
    st.dataframe(
        [
            {"Nome": row[1], "CPF": row[0], "Nascimento": format_birth_date(row[2])}
            for row in CUSTOMERS_ROWS
        ],
        hide_index=True,
    )
    for title, hint in SCENARIOS:
        st.markdown(f"**{title}**  \n{hint}")
    with st.expander("Dados gravados"):
        render_saved_data()


def render_header() -> None:
    st.markdown(TOPBAR_CSS, unsafe_allow_html=True)
    with st.container(key="topbar", horizontal=True):
        st.button(
            "",
            icon=":material/add_comment:",
            type="tertiary",
            help=NEW_CONVERSATION,
            on_click=start_new_conversation,
        )
        if st.button("", icon=":material/help_outline:", type="tertiary", help=GUIDE_LABEL):
            show_test_guide()
    st.title(TITLE)
    st.caption(CAPTION)


def render_saved_data() -> None:
    data_dir = default_data_dir()
    for label, filename in (
        ("Solicitações de limite", LIMIT_REQUESTS_FILE),
        ("Clientes", CUSTOMERS_FILE),
    ):
        st.caption(f"{label} · {filename}")
        try:
            _, rows = read_rows(data_dir / filename)
        except StorageError:
            st.warning("Não foi possível ler este arquivo.")
            continue
        if rows:
            st.dataframe(rows, hide_index=True)
        else:
            st.write("Nenhum registro ainda.")


def render(service: ChatService) -> None:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = new_thread_id()
    thread_id: str = st.session_state.thread_id
    service.start(thread_id)

    for role, text in service.history(thread_id):
        with st.chat_message(role, avatar=AVATARS[role]):
            st.write(text)

    failure: tuple[str, str] | None = st.session_state.get("failure")
    if failure is not None:
        for role, text in (("user", failure[0]), ("assistant", failure[1])):
            with st.chat_message(role, avatar=AVATARS[role]):
                st.write(text)

    ended = service.is_ended(thread_id)
    pending: str | None = st.session_state.get("pending_message")
    message = st.chat_input(INPUT_PLACEHOLDER, disabled=ended or pending is not None)
    if message and not ended and pending is None:
        st.session_state.last_activity = time.monotonic()
        st.session_state.pending_message = message
        st.session_state.pop("failure", None)
        st.rerun()

    if pending is not None:
        if not ended:
            with st.chat_message("user", avatar=AVATARS["user"]):
                st.write(pending)
            with (
                st.chat_message("assistant", avatar=AVATARS["assistant"]),
                st.spinner("Atendendo..."),
            ):
                reply = service.send(thread_id, pending)
            if reply.failed:
                st.session_state.failure = (pending, reply.text)
            st.session_state.last_activity = time.monotonic()
        st.session_state.pending_message = None
        st.rerun()

    if not ended and service.idle_timeout > 0:
        watch_idle(service, thread_id)

    if ended:
        st.info(ENDED_NOTICE)


def main() -> None:
    st.set_page_config(page_title=TITLE, page_icon="🏦")
    try:
        service = get_service()
    except ConfigError as exc:
        st.error(str(exc))
        st.stop()
    except StorageError:
        st.error(DATA_ERROR)
        st.stop()
    render_header()
    render(service)


main()
