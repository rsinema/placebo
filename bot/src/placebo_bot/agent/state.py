from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    chat_id: int
    checkin_active: bool
    checkin_metrics: list[dict]  # list of {id, name, question_prompt, response_type}
    checkin_current_index: int
    checkin_responses: list[dict]  # list of {metric_id, value, notes}
    pending_metric: dict | None  # {name, question_prompt, response_type}
    response_text: str
