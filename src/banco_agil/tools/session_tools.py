from langchain_core.tools import BaseTool, StructuredTool


class SessionTurn:
    def __init__(self) -> None:
        self.ended = False


def build_session_tools(turn: SessionTurn) -> list[BaseTool]:
    def end_conversation() -> str:
        """End the service when the customer wants to finish. Then say goodbye."""
        turn.ended = True
        return "Conversation ended."

    return [StructuredTool.from_function(end_conversation)]


END_RULE = (
    "- If the customer wants to finish the conversation at any point, call "
    "end_conversation and say a short goodbye.\n"
)
