import time
import uuid

import streamlit as st

from banco_agil.config import ConfigError
from banco_agil.service import ChatService, create_service
from banco_agil.storage import StorageError

TITLE = "Banco Ágil"
INPUT_PLACEHOLDER = "Digite sua mensagem"
ENDED_NOTICE = "Atendimento encerrado."
NEW_CONVERSATION = "Nova conversa"
IDLE_CHECK_SECONDS = 5
DATA_ERROR = (
    "Não foi possível preparar os dados do atendimento. Verifique as permissões da pasta de dados."
)


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


def render(service: ChatService) -> None:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = new_thread_id()
    thread_id: str = st.session_state.thread_id
    service.start(thread_id)

    for role, text in service.history(thread_id):
        with st.chat_message(role):
            st.write(text)

    ended = service.is_ended(thread_id)
    message = st.chat_input(INPUT_PLACEHOLDER, disabled=ended)
    if message and not ended:
        st.session_state.last_activity = time.monotonic()
        with st.chat_message("user"):
            st.write(message)
        with st.chat_message("assistant"):
            with st.spinner("Atendendo..."):
                reply = service.send(thread_id, message)
            st.write(reply.text)
        st.session_state.last_activity = time.monotonic()
        if reply.ended:
            st.rerun()

    if not ended and service.idle_timeout > 0:
        watch_idle(service, thread_id)

    if ended:
        st.info(ENDED_NOTICE)
        if st.button(NEW_CONVERSATION):
            st.session_state.thread_id = new_thread_id()
            st.session_state.pop("last_activity", None)
            st.rerun()


def main() -> None:
    st.set_page_config(page_title=TITLE, page_icon="🏦")
    st.title(TITLE)
    try:
        service = get_service()
    except ConfigError as exc:
        st.error(str(exc))
        st.stop()
    except StorageError:
        st.error(DATA_ERROR)
        st.stop()
    render(service)


main()
