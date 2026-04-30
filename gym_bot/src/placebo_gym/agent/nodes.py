import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from placebo_gym import db
from placebo_gym.agent.prompts import (
    CLASSIFY_INTENT_PROMPT,
    GENERAL_CHAT_PROMPT,
    PARSE_WORKOUT_PROMPT,
)
from placebo_gym.agent.state import AgentState
from placebo_gym.config import settings

logger = logging.getLogger(__name__)

_MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"

_llm = ChatOpenAI(
    model="kimi-k2-0905-preview",
    base_url=_MOONSHOT_BASE_URL,
    api_key=settings.moonshot_api_key,
    max_tokens=512,
)

_llm_general = ChatOpenAI(
    model="kimi-k2-0905-preview",
    base_url=_MOONSHOT_BASE_URL,
    api_key=settings.moonshot_api_key,
    max_tokens=512,
)


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return json.loads(text.strip())


def _format_set(s: dict) -> str:
    weight = s.get("weight")
    reps = s["reps"]
    if weight is None:
        return f"{reps}"
    weight_str = f"{int(weight)}" if float(weight) == int(weight) else f"{weight}"
    return f"{reps}@{weight_str}"


def _format_log_summary(exercise_name: str, sets: list[dict]) -> str:
    pretty_name = exercise_name.replace("_", " ")
    set_strs = " / ".join(_format_set(s) for s in sets)
    return f"Logged: **{pretty_name}** — {set_strs}"


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------


async def classify_intent(state: AgentState) -> dict:
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
# Workout logging
# ---------------------------------------------------------------------------


async def handle_log_workout(state: AgentState) -> dict:
    last_msg = state["messages"][-1].content
    prompt = PARSE_WORKOUT_PROMPT.format(message=last_msg)
    resp = await _llm.ainvoke([HumanMessage(content=prompt)])

    try:
        parsed = _parse_json(resp.content)
        exercise_name = parsed["exercise"].strip().lower()
        sets = parsed["sets"]
        if not isinstance(sets, list) or not sets:
            raise ValueError("no sets parsed")
        for s in sets:
            int(s["reps"])  # validate
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as e:
        logger.warning("Failed to parse workout: %s — %s", resp.content, e)
        return {
            "response_text": (
                "I couldn't parse that. Try a format like "
                "**squat 3x3 225 235 255** or **pullups 3x8**."
            ),
        }

    exercise = await db.upsert_exercise(exercise_name)
    log_group_id, _saved = await db.save_exercise_sets(exercise.id, sets)

    summary = _format_log_summary(exercise.name, sets)
    return {
        "last_log_group_id": log_group_id,
        "response_text": f'{summary}\n\nReply "undo" to remove these sets.',
    }


# ---------------------------------------------------------------------------
# Show exercises / recent
# ---------------------------------------------------------------------------


async def handle_show_exercises(state: AgentState) -> dict:
    exercises = await db.get_all_exercises()
    if not exercises:
        return {
            "response_text": "No exercises logged yet. Try something like **squat 3x5 225**.",
        }
    lines = [f"• {e.name.replace('_', ' ')}" for e in exercises]
    return {"response_text": "**Exercises:**\n" + "\n".join(lines)}


async def handle_show_recent(state: AgentState) -> dict:
    rows = await db.get_recent_sets(limit=15)
    if not rows:
        return {"response_text": "No workouts logged yet."}

    # Group consecutive rows with the same log_group_id
    groups: list[list[dict]] = []
    current_group_id = None
    for row in rows:
        if row["log_group_id"] != current_group_id:
            groups.append([row])
            current_group_id = row["log_group_id"]
        else:
            groups[-1].append(row)

    lines = []
    for group in groups[:8]:
        # Newest first; sets within a group come in reverse order from query → re-sort
        group_sorted = sorted(group, key=lambda r: r["set_number"])
        name = group_sorted[0]["exercise_name"].replace("_", " ")
        date = group_sorted[0]["logged_at"].strftime("%m/%d")
        set_strs = " / ".join(
            _format_set({"reps": r["reps"], "weight": float(r["weight"]) if r["weight"] is not None else None})
            for r in group_sorted
        )
        lines.append(f"• {date} — **{name}** {set_strs}")

    return {"response_text": "**Recent workouts:**\n" + "\n".join(lines)}


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------


async def handle_undo(state: AgentState) -> dict:
    log_group_id = state.get("last_log_group_id")
    if log_group_id is None:
        # Fall back to the most recent group in the DB
        log_group_id = await db.get_last_log_group()

    if log_group_id is None:
        return {"response_text": "Nothing to undo."}

    # Capture summary before deleting
    sets = await db.get_log_group_sets(log_group_id)
    deleted = await db.delete_log_group(log_group_id)
    if deleted == 0:
        return {
            "last_log_group_id": None,
            "response_text": "Nothing to undo (those sets are already gone).",
        }

    return {
        "last_log_group_id": None,
        "response_text": f"Removed {deleted} set{'s' if deleted != 1 else ''}.",
    }


# ---------------------------------------------------------------------------
# General fallback
# ---------------------------------------------------------------------------


async def handle_general(state: AgentState) -> dict:
    messages = [SystemMessage(content=GENERAL_CHAT_PROMPT)] + list(state["messages"][-5:])
    resp = await _llm_general.ainvoke(messages)
    return {"response_text": resp.content}
