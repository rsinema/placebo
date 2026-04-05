from langgraph.graph import END, StateGraph

from placebo_analytics.agent.deep import handle_deep_analysis
from placebo_analytics.agent.nodes import (
    classify_intent,
    handle_boolean_frequency,
    handle_clarification,
    handle_correlation,
    handle_correlation_ranking,
    handle_experiment_analysis,
    handle_metric_summary,
    handle_multi_metric_overview,
    handle_period_comparison,
    handle_streak,
    handle_trend,
    reset_turn,
)
from placebo_analytics.agent.state import AnalyticsState

CONFIDENCE_THRESHOLD = 0.5


def _route_intent(state: AnalyticsState) -> str:
    confidence = state.get("classification_confidence", 1.0)
    intent = state.get("intent", "general")

    # Low confidence -> ask for clarification (but not for "general" fallback)
    if confidence < CONFIDENCE_THRESHOLD and intent != "general":
        return "handle_clarification"

    return {
        "metric_summary": "handle_metric_summary",
        "trend": "handle_trend",
        "correlation": "handle_correlation",
        "experiment_analysis": "handle_experiment_analysis",
        "multi_metric_overview": "handle_multi_metric_overview",
        "period_comparison": "handle_period_comparison",
        "streak": "handle_streak",
        "correlation_ranking": "handle_correlation_ranking",
        "boolean_frequency": "handle_boolean_frequency",
        "deep_analysis": "handle_deep_analysis",
        "recommendation": "handle_deep_analysis",
        "anomaly_explanation": "handle_deep_analysis",
        "general": "handle_deep_analysis",
    }.get(intent, "handle_deep_analysis")


def build_graph(checkpointer=None) -> StateGraph:
    graph = StateGraph(AnalyticsState)

    graph.add_node("reset_turn", reset_turn)
    graph.add_node("classify_intent", classify_intent)
    graph.add_node("handle_clarification", handle_clarification)
    graph.add_node("handle_metric_summary", handle_metric_summary)
    graph.add_node("handle_trend", handle_trend)
    graph.add_node("handle_correlation", handle_correlation)
    graph.add_node("handle_experiment_analysis", handle_experiment_analysis)
    graph.add_node("handle_multi_metric_overview", handle_multi_metric_overview)
    graph.add_node("handle_period_comparison", handle_period_comparison)
    graph.add_node("handle_streak", handle_streak)
    graph.add_node("handle_correlation_ranking", handle_correlation_ranking)
    graph.add_node("handle_boolean_frequency", handle_boolean_frequency)
    graph.add_node("handle_deep_analysis", handle_deep_analysis)

    graph.set_entry_point("reset_turn")
    graph.add_edge("reset_turn", "classify_intent")

    graph.add_conditional_edges(
        "classify_intent",
        _route_intent,
        {
            "handle_clarification": "handle_clarification",
            "handle_metric_summary": "handle_metric_summary",
            "handle_trend": "handle_trend",
            "handle_correlation": "handle_correlation",
            "handle_experiment_analysis": "handle_experiment_analysis",
            "handle_multi_metric_overview": "handle_multi_metric_overview",
            "handle_period_comparison": "handle_period_comparison",
            "handle_streak": "handle_streak",
            "handle_correlation_ranking": "handle_correlation_ranking",
            "handle_boolean_frequency": "handle_boolean_frequency",
            "handle_deep_analysis": "handle_deep_analysis",
        },
    )

    for node in [
        "handle_clarification",
        "handle_metric_summary",
        "handle_trend",
        "handle_correlation",
        "handle_experiment_analysis",
        "handle_multi_metric_overview",
        "handle_period_comparison",
        "handle_streak",
        "handle_correlation_ranking",
        "handle_boolean_frequency",
        "handle_deep_analysis",
    ]:
        graph.add_edge(node, END)

    return graph.compile(checkpointer=checkpointer)


# Lazy-initialized by init_graph() during app startup
agent_graph = None


def init_graph(checkpointer=None):
    global agent_graph
    agent_graph = build_graph(checkpointer=checkpointer)
    return agent_graph
