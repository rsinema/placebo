from langgraph.graph import END, StateGraph

from placebo_gym.agent.nodes import (
    classify_intent,
    handle_general,
    handle_log_workout,
    handle_show_exercises,
    handle_show_recent,
    handle_undo,
)
from placebo_gym.agent.state import AgentState


def _route_intent(state: AgentState) -> str:
    intent = state.get("intent", "general")
    return {
        "log_workout": "handle_log_workout",
        "show_exercises": "handle_show_exercises",
        "show_recent": "handle_show_recent",
        "undo": "handle_undo",
        "general": "handle_general",
    }.get(intent, "handle_general")


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("classify_intent", classify_intent)
    graph.add_node("handle_log_workout", handle_log_workout)
    graph.add_node("handle_show_exercises", handle_show_exercises)
    graph.add_node("handle_show_recent", handle_show_recent)
    graph.add_node("handle_undo", handle_undo)
    graph.add_node("handle_general", handle_general)

    graph.set_entry_point("classify_intent")

    graph.add_conditional_edges(
        "classify_intent",
        _route_intent,
        {
            "handle_log_workout": "handle_log_workout",
            "handle_show_exercises": "handle_show_exercises",
            "handle_show_recent": "handle_show_recent",
            "handle_undo": "handle_undo",
            "handle_general": "handle_general",
        },
    )

    for node in [
        "handle_log_workout",
        "handle_show_exercises",
        "handle_show_recent",
        "handle_undo",
        "handle_general",
    ]:
        graph.add_edge(node, END)

    return graph.compile()


agent_graph = build_graph()
