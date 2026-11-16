import logging
from collections.abc import Callable
from datetime import datetime

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig

from banco_agil.graph.state import GraphState
from banco_agil.guardrails import (
    BLOCKED_INPUT_REPLY,
    CLOSING_REPLY,
    SAFE_OUTPUT_REPLY,
    GuardContext,
    Guardrail,
)
from banco_agil.logging_utils import get_logger, log_event

logger = get_logger(__name__)

MAX_BLOCKED_STREAK = 3


def _thread_id(config: RunnableConfig | None) -> str:
    configurable = (config or {}).get("configurable") or {}
    return str(configurable.get("thread_id", "unknown"))


def _log_block(
    direction: str, reason: str | None, thread_id: str, clock: Callable[[], datetime]
) -> None:
    log_event(
        logger,
        "guard_blocked",
        level=logging.WARNING,
        direction=direction,
        reason=reason,
        thread=thread_id,
        at=clock().isoformat(timespec="seconds"),
    )


def make_input_guard_node(
    guardrail: Guardrail, clock: Callable[[], datetime] = datetime.now
) -> Callable[[GraphState, RunnableConfig], dict[str, object]]:
    def input_guard(state: GraphState, config: RunnableConfig) -> dict[str, object]:
        last = next(
            (m for m in reversed(state.get("messages", [])) if isinstance(m, HumanMessage)), None
        )
        if last is None:
            return {"blocked_input": False}
        thread_id = _thread_id(config)
        context = GuardContext(state.get("customer_cpf"), thread_id)
        text = last.content if isinstance(last.content, str) else ""
        result = guardrail.check_input(text, context)
        if result.allowed:
            return {"blocked_input": False, "blocked_streak": 0}

        _log_block("input", result.reason, thread_id, clock)
        streak = state.get("blocked_streak", 0) + 1
        removal: list[BaseMessage] = [RemoveMessage(id=last.id)] if last.id else []
        if streak >= MAX_BLOCKED_STREAK:
            return {
                "messages": [*removal, AIMessage(content=CLOSING_REPLY)],
                "blocked_input": True,
                "blocked_streak": streak,
                "phase": "ended",
            }
        return {
            "messages": [*removal, AIMessage(content=BLOCKED_INPUT_REPLY)],
            "blocked_input": True,
            "blocked_streak": streak,
        }

    return input_guard


def make_output_guard_node(
    guardrail: Guardrail, clock: Callable[[], datetime] = datetime.now
) -> Callable[[GraphState, RunnableConfig], dict[str, object]]:
    def output_guard(state: GraphState, config: RunnableConfig) -> dict[str, object]:
        thread_id = _thread_id(config)
        context = GuardContext(state.get("customer_cpf"), thread_id)
        replaced: list[BaseMessage] = []
        for message in reversed(state.get("messages", [])):
            if isinstance(message, HumanMessage):
                break
            if not isinstance(message, AIMessage) or not isinstance(message.content, str):
                continue
            result = guardrail.check_output(message.content, context)
            if not result.allowed:
                _log_block("output", result.reason, thread_id, clock)
                replaced.append(AIMessage(content=SAFE_OUTPUT_REPLY, id=message.id))
        return {"messages": replaced} if replaced else {}

    return output_guard
