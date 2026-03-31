import json
import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from placebo_bot.agent.prompts import (
    CLASSIFY_INTENT_PROMPT,
    GENERAL_CHAT_PROMPT,
    GENERATE_METRIC_PROMPT,
    PARSE_CHECKIN_RESPONSE_PROMPT,
)
from placebo_bot.agent.state import AgentState
from placebo_bot.config import settings
from placebo_bot import db

logger = logging.getLogger(__name__)

_MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"

_llm = ChatOpenAI(
    model="kimi-k2-0905-preview",
    base_url=_MOONSHOT_BASE_URL,
    api_key=settings.moonshot_api_key,
    max_tokens=256,
)

_llm_general = ChatOpenAI(
    model="kimi-k2-0905-preview",
    base_url=_MOONSHOT_BASE_URL,
    api_key=settings.moonshot_api_key,
    max_tokens=1024,
)


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------


async def classify_intent(state: AgentState) -> dict:
    # If check-in is active and user isn't issuing a command override, treat as response
    if state.get("checkin_active") and state["checkin_current_index"] < len(
        state.get("checkin_metrics", [])
    ):
        last_msg = state["messages"][-1].content if state["messages"] else ""
        # Quick check: if it starts with a slash command, classify normally
        if not last_msg.startswith("/"):
            return {"intent": "checkin_response"}

    last_msg = state["messages"][-1].content if state["messages"] else ""
    resp = await _llm.ainvoke(
        [SystemMessage(content=CLASSIFY_INTENT_PROMPT), HumanMessage(content=last_msg)]
    )
    try:
        result = _parse_json(resp.content)
        return {"intent": result["intent"]}
    except (json.JSONDecodeError, KeyError):
        logger.warning("Failed to parse intent: %s", resp.content)
        return {"intent": "general"}


# ---------------------------------------------------------------------------
# Check-in flow
# ---------------------------------------------------------------------------


async def start_checkin(state: AgentState) -> dict:
    metrics = await db.get_active_metrics()
    if not metrics:
        return {
            "response_text": "You don't have any active metrics yet. Try adding one with something like 'add a metric for sleep quality'.",
            "checkin_active": False,
        }

    metric_dicts = [
        {
            "id": str(m.id),
            "name": m.name,
            "question_prompt": m.question_prompt,
            "response_type": m.response_type,
        }
        for m in metrics
    ]
    first = metric_dicts[0]
    return {
        "checkin_active": True,
        "checkin_metrics": metric_dicts,
        "checkin_current_index": 0,
        "checkin_responses": [],
        "response_text": f"Let's do your check-in! ({len(metric_dicts)} questions)\n\n{first['question_prompt']}",
    }


async def process_checkin_response(state: AgentState) -> dict:
    metrics = state["checkin_metrics"]
    idx = state["checkin_current_index"]
    current_metric = metrics[idx]

    last_msg = state["messages"][-1].content
    prompt = PARSE_CHECKIN_RESPONSE_PROMPT.format(
        question=current_metric["question_prompt"],
        response_type=current_metric["response_type"],
        answer=last_msg,
    )
    resp = await _llm.ainvoke([HumanMessage(content=prompt)])

    try:
        parsed = _parse_json(resp.content)
        value = str(parsed["value"])
        notes = parsed.get("notes")
    except (json.JSONDecodeError, KeyError):
        value = last_msg
        notes = None

    # Save to database
    from uuid import UUID

    await db.save_checkin_response(UUID(current_metric["id"]), value, notes)

    responses = state.get("checkin_responses", []) + [
        {"metric_id": current_metric["id"], "value": value, "notes": notes}
    ]
    next_idx = idx + 1

    return {
        "checkin_responses": responses,
        "checkin_current_index": next_idx,
    }


async def ask_next_or_complete(state: AgentState) -> dict:
    metrics = state["checkin_metrics"]
    idx = state["checkin_current_index"]

    if idx >= len(metrics):
        # Check-in complete
        count = len(state["checkin_responses"])
        return {
            "checkin_active": False,
            "response_text": f"Check-in complete! Logged {count} responses. Nice work!",
        }

    next_metric = metrics[idx]
    return {"response_text": next_metric["question_prompt"]}


# ---------------------------------------------------------------------------
# Metric management
# ---------------------------------------------------------------------------


async def handle_add_metric(state: AgentState) -> dict:
    last_msg = state["messages"][-1].content
    prompt = GENERATE_METRIC_PROMPT.format(user_input=last_msg)
    resp = await _llm.ainvoke([HumanMessage(content=prompt)])

    try:
        metric_def = _parse_json(resp.content)
    except (json.JSONDecodeError, KeyError):
        return {
            "response_text": "I had trouble understanding that. Could you describe the metric you want to add?",
            "pending_metric": None,
        }

    return {
        "pending_metric": metric_def,
        "response_text": (
            f"I'll create this metric:\n\n"
            f"**{metric_def['name']}**\n"
            f"Question: {metric_def['question_prompt']}\n"
            f"Type: {metric_def['response_type']}\n\n"
            f"Does that look good? (yes/no)"
        ),
    }


async def confirm_metric(state: AgentState) -> dict:
    pending = state.get("pending_metric")
    if not pending:
        return {"response_text": "Nothing to confirm."}

    existing = await db.get_metric_by_name(pending["name"], active_only=False)
    if existing:
        if existing.active:
            return {
                "pending_metric": None,
                "response_text": f"A metric named **{existing.name}** already exists.",
            }
        metric = await db.reactivate_metric(
            existing.id, pending["question_prompt"], pending["response_type"]
        )
        return {
            "pending_metric": None,
            "response_text": f"Reactivated metric **{metric.name}**! It will be included in your next check-in.",
        }

    metric = await db.create_metric(
        pending["name"], pending["question_prompt"], pending["response_type"]
    )
    return {
        "pending_metric": None,
        "response_text": f"Added metric **{metric.name}**! It will be included in your next check-in.",
    }


async def handle_remove_metric(state: AgentState) -> dict:
    last_msg = state["messages"][-1].content
    # Try to find the metric name in the message
    metrics = await db.get_active_metrics()
    best_match = None
    msg_lower = last_msg.lower()
    for m in metrics:
        if m.name.lower() in msg_lower or m.name.replace("_", " ").lower() in msg_lower:
            best_match = m
            break

    if not best_match:
        names = ", ".join(m.name for m in metrics)
        return {
            "response_text": f"I couldn't find that metric. Active metrics: {names}",
        }

    await db.archive_metric(best_match.id)
    return {
        "response_text": f"Archived **{best_match.name}**. Historical data is preserved.",
    }


async def handle_show_metrics(state: AgentState) -> dict:
    metrics = await db.get_active_metrics()
    if not metrics:
        return {"response_text": "No active metrics. Add one by saying something like 'add a metric for mood'."}

    lines = [f"• **{m.name}** ({m.response_type}) — {m.question_prompt}" for m in metrics]
    return {"response_text": "**Active metrics:**\n" + "\n".join(lines)}


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


async def handle_start_experiment(state: AgentState) -> dict:
    last_msg = state["messages"][-1].content
    # Extract experiment name — everything after "experiment" keyword
    name = last_msg
    for prefix in ["start experiment:", "start experiment", "new experiment:", "new experiment"]:
        if name.lower().startswith(prefix):
            name = name[len(prefix) :].strip()
            break

    active = await db.get_active_experiments()
    warning = ""
    if active:
        names = ", ".join(e.name for e in active)
        warning = f"\n\n⚠️ You have active experiments ({names}). Overlapping experiments make attribution harder."

    exp = await db.create_experiment(name)
    return {
        "response_text": f"Started experiment: **{exp.name}**{warning}",
    }


async def handle_end_experiment(state: AgentState) -> dict:
    last_msg = state["messages"][-1].content
    active = await db.get_active_experiments()

    if not active:
        return {"response_text": "No active experiments to end."}

    # Try to match by name
    msg_lower = last_msg.lower()
    match = None
    for e in active:
        if e.name.lower() in msg_lower:
            match = e
            break

    if not match:
        if len(active) == 1:
            match = active[0]
        else:
            names = ", ".join(e.name for e in active)
            return {
                "response_text": f"Which experiment? Active: {names}",
            }

    await db.end_experiment(match.id)
    return {"response_text": f"Ended experiment: **{match.name}**"}


async def handle_show_experiments(state: AgentState) -> dict:
    experiments = await db.get_all_experiments()
    if not experiments:
        return {"response_text": "No experiments yet. Start one by saying something like 'start experiment: creatine 5g daily'."}

    lines = []
    for e in experiments:
        status = "ongoing" if e.ended_at is None else f"ended {e.ended_at:%Y-%m-%d}"
        lines.append(f"• **{e.name}** (started {e.started_at:%Y-%m-%d}, {status})")

    return {"response_text": "**Experiments:**\n" + "\n".join(lines)}


# ---------------------------------------------------------------------------
# Other
# ---------------------------------------------------------------------------


async def handle_skip(state: AgentState) -> dict:
    return {
        "checkin_active": False,
        "checkin_current_index": 0,
        "checkin_metrics": [],
        "checkin_responses": [],
        "response_text": "Skipped today's check-in. No worries, see you tomorrow!",
    }


async def handle_set_schedule(state: AgentState) -> dict:
    last_msg = state["messages"][-1].content
    # Try to extract HH:MM
    import re

    match = re.search(r"(\d{1,2}):(\d{2})", last_msg)
    if not match:
        return {"response_text": "Please provide a time in HH:MM format (24h). Example: 'set check-in to 09:00'"}

    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return {"response_text": "Invalid time. Use 24h format, e.g. 14:30."}

    await db.set_bot_setting("checkin_hour", str(hour))
    await db.set_bot_setting("checkin_minute", str(minute))

    return {
        "response_text": f"Check-in time set to {hour:02d}:{minute:02d} UTC. I'll update the schedule.",
    }


async def handle_general(state: AgentState) -> dict:
    messages = [SystemMessage(content=GENERAL_CHAT_PROMPT)] + list(state["messages"][-5:])
    resp = await _llm_general.ainvoke(messages)
    return {"response_text": resp.content}
