from langgraph.graph import END, StateGraph

from placebo_bot.agent.nodes import (
    ask_next_or_complete,
    classify_intent,
    confirm_metric,
    handle_add_metric,
    handle_end_experiment,
    handle_general,
    handle_remove_metric,
    handle_set_schedule,
    handle_show_experiments,
    handle_show_metrics,
    handle_skip,
    handle_start_experiment,
    process_checkin_response,
    start_checkin,
)
from placebo_bot.agent.state import AgentState


def _route_intent(state: AgentState) -> str:
    intent = state.get("intent", "general")

    # If there's a pending metric and user confirms, route to confirm
    if state.get("pending_metric") and intent == "confirm":
        return "confirm_metric"

    return {
        "checkin_response": "process_checkin_response",
        "add_metric": "handle_add_metric",
        "remove_metric": "handle_remove_metric",
        "show_metrics": "handle_show_metrics",
        "start_experiment": "handle_start_experiment",
        "end_experiment": "handle_end_experiment",
        "show_experiments": "handle_show_experiments",
        "skip_today": "handle_skip",
        "set_schedule": "handle_set_schedule",
        "start_checkin": "start_checkin",
        "confirm": "confirm_metric",
        "general": "handle_general",
    }.get(intent, "handle_general")


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("start_checkin", start_checkin)
    graph.add_node("process_checkin_response", process_checkin_response)
    graph.add_node("ask_next_or_complete", ask_next_or_complete)
    graph.add_node("handle_add_metric", handle_add_metric)
    graph.add_node("confirm_metric", confirm_metric)
    graph.add_node("handle_remove_metric", handle_remove_metric)
    graph.add_node("handle_show_metrics", handle_show_metrics)
    graph.add_node("handle_start_experiment", handle_start_experiment)
    graph.add_node("handle_end_experiment", handle_end_experiment)
    graph.add_node("handle_show_experiments", handle_show_experiments)
    graph.add_node("handle_skip", handle_skip)
    graph.add_node("handle_set_schedule", handle_set_schedule)
    graph.add_node("handle_general", handle_general)

    # Entry point
    graph.set_entry_point("classify_intent")

    # Route from intent classification
    graph.add_conditional_edges(
        "classify_intent",
        _route_intent,
        {
            "start_checkin": "start_checkin",
            "process_checkin_response": "process_checkin_response",
            "handle_add_metric": "handle_add_metric",
            "confirm_metric": "confirm_metric",
            "handle_remove_metric": "handle_remove_metric",
            "handle_show_metrics": "handle_show_metrics",
            "handle_start_experiment": "handle_start_experiment",
            "handle_end_experiment": "handle_end_experiment",
            "handle_show_experiments": "handle_show_experiments",
            "handle_skip": "handle_skip",
            "handle_set_schedule": "handle_set_schedule",
            "handle_general": "handle_general",
        },
    )

    # Check-in response -> ask next or complete
    graph.add_edge("process_checkin_response", "ask_next_or_complete")

    # Terminal edges
    for node in [
        "start_checkin",
        "ask_next_or_complete",
        "handle_add_metric",
        "confirm_metric",
        "handle_remove_metric",
        "handle_show_metrics",
        "handle_start_experiment",
        "handle_end_experiment",
        "handle_show_experiments",
        "handle_skip",
        "handle_set_schedule",
        "handle_general",
    ]:
        graph.add_edge(node, END)

    return graph.compile()


agent_graph = build_graph()
