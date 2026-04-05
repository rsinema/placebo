from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class AnalyticsState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str
    chat_id: int
    response_text: str
    chart_bytes: bytes | None
    suggested_followups: list[str]
    classification_confidence: float
    alternative_intents: list[dict]
