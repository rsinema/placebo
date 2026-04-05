import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from placebo_analytics import db
from placebo_analytics.agent.nodes import _build_ai_message
from placebo_analytics.agent.prompts import DEEP_ANALYSIS_SYSTEM_PROMPT, GENERAL_ANALYTICS_PROMPT
from placebo_analytics.agent.state import AnalyticsState
from placebo_analytics.agent.tools import ALL_TOOLS
from placebo_analytics.config import settings

logger = logging.getLogger(__name__)

_MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"

_llm_deep = ChatOpenAI(
    model="kimi-k2-0905-preview",
    base_url=_MOONSHOT_BASE_URL,
    api_key=settings.moonshot_api_key,
    max_tokens=1024,
)

# Fallback LLM for when the ReAct agent errors out
_llm_fallback = ChatOpenAI(
    model="kimi-k2-0905-preview",
    base_url=_MOONSHOT_BASE_URL,
    api_key=settings.moonshot_api_key,
    max_tokens=1024,
)

_deep_agent = None


def _build_deep_agent():
    """Build the ReAct agent subgraph. Called lazily on first use."""
    return create_react_agent(
        model=_llm_deep,
        tools=ALL_TOOLS,
    )


def _get_deep_agent():
    global _deep_agent
    if _deep_agent is None:
        _deep_agent = _build_deep_agent()
    return _deep_agent


async def handle_deep_analysis(state: AnalyticsState) -> dict:
    """Parent graph node that invokes the ReAct tool-calling agent.

    Routes complex, open-ended, and multi-step questions through a ReAct loop
    that can chain multiple data queries before synthesizing a response.

    Falls back to a simple LLM response if the ReAct agent errors out.
    """
    messages = state.get("messages", [])
    last_msg = messages[-1].content if messages else ""

    # Build system prompt with current metric list
    try:
        active_metrics = await db.get_active_metrics()
        available_metrics = (
            ", ".join(m.name for m in active_metrics) if active_metrics else "(no metrics configured)"
        )
    except Exception:
        available_metrics = "(unable to fetch metrics)"

    system_prompt = DEEP_ANALYSIS_SYSTEM_PROMPT.format(available_metrics=available_metrics)

    try:
        agent = _get_deep_agent()

        # Build input messages: system prompt + conversation history
        agent_messages = [SystemMessage(content=system_prompt)] + list(messages)

        result = await agent.ainvoke(
            {"messages": agent_messages},
            {"recursion_limit": 9},
        )

        # Extract the final non-tool-call AI response
        agent_messages_out = result.get("messages", [])
        final_response = ""
        for msg in reversed(agent_messages_out):
            if isinstance(msg, AIMessage) and msg.content and not getattr(msg, "tool_calls", None):
                final_response = msg.content
                break

        if not final_response:
            final_response = "I explored your data but couldn't formulate a clear answer. Could you rephrase your question?"

    except Exception:
        logger.exception("Deep analysis agent failed, falling back to general handler")
        # Fallback: simple LLM response without data access (same as handle_general)
        prompt = GENERAL_ANALYTICS_PROMPT.format(question=last_msg)
        try:
            resp = await _llm_fallback.ainvoke([HumanMessage(content=prompt)])
            final_response = resp.content
        except Exception:
            final_response = (
                "I had trouble analyzing that. Try asking about a specific metric's trend, "
                "a correlation between two metrics, or your consistency over the last 30 days."
            )

    followups = [
        "Want me to dig deeper into any specific metric?",
        "Ask me a follow-up question about your data.",
    ]
    return {
        "response_text": final_response,
        "messages": [_build_ai_message(final_response, followups)],
        "chart_bytes": None,
        "suggested_followups": followups,
    }
