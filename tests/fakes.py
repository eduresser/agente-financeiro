from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import BaseModel, PrivateAttr


class ScriptedChatModel(BaseChatModel):
    script: list[AIMessage | Exception]
    _calls: int = PrivateAttr(default=0)
    _seen: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def seen(self) -> list[list[BaseMessage]]:
        return self._seen

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._seen.append(list(messages))
        if self._calls >= len(self.script):
            raise AssertionError("scripted model ran out of responses")
        item = self.script[self._calls]
        self._calls += 1
        if isinstance(item, Exception):
            raise item
        return ChatResult(generations=[ChatGeneration(message=item)])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        model = self

        class _Structured:
            def invoke(self, messages: Any, *args: Any, **kw: Any) -> Any:
                reply = model.invoke(messages)
                content = reply.content if isinstance(reply.content, str) else ""
                if isinstance(schema, type) and issubclass(schema, BaseModel):
                    return schema.model_validate_json(content)
                return content

        return _Structured()


def ai(text: str) -> AIMessage:
    return AIMessage(content=text)


def ai_tool_call(name: str, args: dict[str, Any], call_id: str = "call-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


__all__ = ["ScriptedChatModel", "ai", "ai_tool_call", "BaseTool"]
