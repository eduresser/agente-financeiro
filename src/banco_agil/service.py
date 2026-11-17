import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph

from banco_agil.config import Settings, get_settings
from banco_agil.exchange import AwesomeApiProvider
from banco_agil.graph.builder import build_graph
from banco_agil.graph.triage import GREETING
from banco_agil.guardrails import LocalGuardrail, other_customers_patterns
from banco_agil.guardrails.judge import ModelJudge
from banco_agil.llm import build_chat_model
from banco_agil.logging_utils import get_logger, log_event
from banco_agil.observability import build_callbacks
from banco_agil.seed import bootstrap
from banco_agil.storage import (
    CustomerRepository,
    LimitRequestRepository,
    ScoreLimitRepository,
    default_data_dir,
)

logger = get_logger(__name__)

FRIENDLY_ERROR = (
    "Tive um problema técnico agora e não consegui responder. "
    "Pode enviar a sua mensagem de novo em instantes?"
)
TIMEOUT_REPLY = (
    "Estou encerrando o atendimento por inatividade. "
    "Obrigado por procurar o Banco Ágil, e até a próxima!"
)
JUDGE_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class Reply:
    text: str
    ended: bool = False
    failed: bool = False


def open_checkpointer(path: Path) -> SqliteSaver:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(connection)


class ChatService:
    def __init__(
        self,
        graph: CompiledStateGraph[Any, Any, Any, Any],
        callbacks: Sequence[BaseCallbackHandler] = (),
        idle_timeout: int = 0,
    ) -> None:
        self._graph = graph
        self._callbacks = list(callbacks)
        self.idle_timeout = idle_timeout

    def start(self, thread_id: str) -> None:
        if self.history(thread_id):
            return
        self._append(thread_id, GREETING, {})

    def close_for_timeout(self, thread_id: str) -> Reply:
        if self.is_ended(thread_id):
            return Reply(TIMEOUT_REPLY, ended=True)
        self._append(
            thread_id, TIMEOUT_REPLY, {"phase": "ended", "pending_limit": None, "interview": {}}
        )
        return Reply(TIMEOUT_REPLY, ended=self.is_ended(thread_id))

    def _append(self, thread_id: str, text: str, extra: dict[str, Any]) -> None:
        try:
            self._graph.update_state(
                self._config(thread_id),
                {"messages": [AIMessage(content=text)], **extra},
                as_node="output_guard",
            )
        except Exception as exc:
            log_event(
                logger,
                "state_update_failed",
                level=logging.ERROR,
                thread=thread_id,
                error=type(exc).__name__,
            )

    def send(self, thread_id: str, text: str) -> Reply:
        config = self._config(thread_id)
        try:
            known = self._message_ids(config)
        except Exception:
            known = set()
        try:
            result = self._graph.invoke({"messages": [HumanMessage(content=text)]}, config)
        except Exception as exc:
            log_event(
                logger,
                "turn_failed",
                level=logging.ERROR,
                thread=thread_id,
                error=type(exc).__name__,
            )
            self._rollback(config, known, thread_id)
            return Reply(FRIENDLY_ERROR, ended=self.is_ended(thread_id), failed=True)
        replies = [
            str(m.content)
            for m in result["messages"]
            if isinstance(m, AIMessage) and m.id not in known
        ]
        return Reply("\n\n".join(replies), ended=result.get("phase") == "ended")

    def is_ended(self, thread_id: str) -> bool:
        try:
            return self._graph.get_state(self._config(thread_id)).values.get("phase") == "ended"
        except Exception:
            return False

    def history(self, thread_id: str) -> list[tuple[str, str]]:
        try:
            messages = self._graph.get_state(self._config(thread_id)).values.get("messages", [])
        except Exception:
            return []
        return [
            ("user" if isinstance(m, HumanMessage) else "assistant", str(m.content))
            for m in messages
            if isinstance(m, HumanMessage | AIMessage)
        ]

    def _config(self, thread_id: str) -> RunnableConfig:
        return {
            "configurable": {"thread_id": thread_id},
            "callbacks": self._callbacks,
            "metadata": {"langfuse_session_id": thread_id},
        }

    def _message_ids(self, config: RunnableConfig) -> set[str | None]:
        values = self._graph.get_state(config).values
        return {m.id for m in values.get("messages", [])}

    def _rollback(self, config: RunnableConfig, known: set[str | None], thread_id: str) -> None:
        try:
            values = self._graph.get_state(config).values
            added = [m for m in values.get("messages", []) if m.id not in known and m.id]
            if added:
                self._graph.update_state(
                    config, {"messages": [RemoveMessage(id=str(m.id)) for m in added]}
                )
        except Exception as exc:
            log_event(
                logger,
                "rollback_failed",
                level=logging.ERROR,
                thread=thread_id,
                error=type(exc).__name__,
            )


def create_service(
    settings: Settings | None = None,
    data_dir: Path | None = None,
    database: Path | None = None,
) -> ChatService:
    settings = settings or get_settings()
    data_dir = data_dir or default_data_dir()
    database = database or data_dir / "runtime" / "conversations.sqlite"
    bootstrap(data_dir)
    customers = CustomerRepository(data_dir / "clientes.csv")
    bands = ScoreLimitRepository(data_dir / "score_limite.csv")
    judge = ModelJudge(build_chat_model(settings, request_timeout=JUDGE_TIMEOUT_SECONDS))
    graph = build_graph(
        model=build_chat_model(settings),
        customers=customers,
        bands=bands,
        requests=LimitRequestRepository(data_dir / "solicitacoes_aumento_limite.csv"),
        exchange=AwesomeApiProvider(settings.exchange_api_base_url),
        guardrail=LocalGuardrail(judge=judge, protected=other_customers_patterns(customers, bands)),
        checkpointer=open_checkpointer(database),
    )
    return ChatService(
        graph, build_callbacks(settings), idle_timeout=settings.session_timeout_seconds
    )
