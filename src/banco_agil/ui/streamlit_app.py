import uuid

import streamlit as st

from banco_agil.config import ConfigError
from banco_agil.service import ChatService, create_service

TITLE = "Banco Ágil"
INPUT_PLACEHOLDER = "Digite sua mensagem"
ENDED_NOTICE = "Atendimento encerrado."
NEW_CONVERSATION = "Nova conversa"


@st.cache_resource
def get_service() -> ChatService:
    return create_service()


def new_thread_id() -> str:
    return uuid.uuid4().hex


def render(service: ChatService) -> None:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = new_thread_id()
    thread_id: str = st.session_state.thread_id

    for role, text in service.history(thread_id):
        with st.chat_message(role):
            st.write(text)

    ended = service.is_ended(thread_id)
    message = st.chat_input(INPUT_PLACEHOLDER, disabled=ended)
    if message and not ended:
        with st.chat_message("user"):
            st.write(message)
        with st.chat_message("assistant"):
            with st.spinner("Atendendo..."):
                reply = service.send(thread_id, message)
            st.write(reply.text)
        if reply.ended:
            st.rerun()

    if ended:
        st.info(ENDED_NOTICE)
        if st.button(NEW_CONVERSATION):
            st.session_state.thread_id = new_thread_id()
            st.rerun()


def main() -> None:
    st.set_page_config(page_title=TITLE, page_icon="🏦")
    st.title(TITLE)
    try:
        service = get_service()
    except ConfigError as exc:
        st.error(str(exc))
        st.stop()
    render(service)


main()
