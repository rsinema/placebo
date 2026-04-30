from typing import Annotated, TypedDict
from uuid import UUID

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    chat_id: int
    last_log_group_id: UUID | None
    response_text: str
