from collections.abc import Callable, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from banco_agil.domain.privacy import Known, messages_for_model
from banco_agil.logging_utils import get_logger

logger = get_logger(__name__)

MAX_STEPS = 10
LOOP_FALLBACK = "Não consegui concluir agora. Pode repetir o que precisa, por favor?"


def _run_tool(tools: dict[str, BaseTool], name: str, args: dict[str, object]) -> str:
    tool = tools.get(name)
    if tool is None:
        return f"Unknown tool {name}."
    try:
        return str(tool.invoke(args))
    except Exception as exc:
        logger.error("tool_failed tool=%s error=%s", name, type(exc).__name__)
        return f"Tool {name} failed: invalid arguments."


def run_tool_loop(
    model: BaseChatModel,
    system_prompt: str,
    history: Sequence[AnyMessage],
    tools: Sequence[BaseTool],
    stop_when: Callable[[], bool] | None = None,
    known: Known = Known(),  # noqa: B008
) -> AIMessage | None:
    by_name = {tool.name: tool for tool in tools}
    bound = model.bind_tools(list(tools))
    messages: list[AnyMessage] = [
        SystemMessage(content=system_prompt),
        *messages_for_model(history, known),
    ]
    for _ in range(MAX_STEPS):
        reply = bound.invoke(messages)
        if not isinstance(reply, AIMessage):
            break
        if not reply.tool_calls:
            return reply
        messages.append(reply)
        for call in reply.tool_calls:
            output = _run_tool(by_name, call["name"], call["args"])
            messages.append(ToolMessage(content=output, tool_call_id=call["id"] or call["name"]))
        if stop_when is not None and stop_when():
            return None
    logger.error("tool_loop_exhausted steps=%s", MAX_STEPS)
    return AIMessage(content=LOOP_FALLBACK)
