import logging
import re

import telegram.error
from langchain_core.messages import HumanMessage
from telegram import Update
from telegram.ext import ContextTypes

from placebo_gym.agent.graph import agent_graph

logger = logging.getLogger(__name__)

# In-memory state store keyed by chat_id
_state_store: dict[int, dict] = {}

# Single-user bot — first /start sets the owner
_authorized_user_id: int | None = None


def _get_state(chat_id: int) -> dict:
    if chat_id not in _state_store:
        _state_store[chat_id] = {
            "messages": [],
            "intent": "",
            "chat_id": chat_id,
            "last_log_group_id": None,
            "response_text": "",
        }
    return _state_store[chat_id]


def _md_to_html(text: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _update_state(chat_id: int, result: dict) -> None:
    state = _state_store.setdefault(chat_id, {})
    state.update(result)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _authorized_user_id
    chat_id = update.effective_chat.id
    user_id = update.message.from_user.id
    if _authorized_user_id is None:
        _authorized_user_id = user_id
    _get_state(chat_id)
    await update.message.reply_text(
        "Welcome to Placebo Gym! 💪\n\n"
        "Log workouts by sending messages like:\n"
        "• <code>squat 3x3 225 235 255</code>\n"
        "• <code>bench 3x5 185</code>\n"
        "• <code>pullups 3x8</code>\n\n"
        "Other things you can say:\n"
        "• <i>show exercises</i> — list exercises you've logged\n"
        "• <i>recent</i> — show recent workouts\n"
        "• <i>undo</i> — remove the last set you logged\n\n"
        "Type /help for more.",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Logging formats I understand:</b>\n\n"
        "• <code>squat 3x3 225 235 255</code> — 3 sets × 3 reps with per-set weights\n"
        "• <code>bench 3x5 185</code> — 3 sets × 5 reps, same weight\n"
        "• <code>pullups 3x8</code> — bodyweight (no weight)\n"
        "• <code>deadlift 5/3/1 315 335 365</code> — varying reps per set\n\n"
        "<b>Other commands:</b>\n"
        "• <i>show exercises</i> — list known exercises\n"
        "• <i>recent</i> or <i>show recent</i> — last few sets\n"
        "• <i>undo</i> — remove the last logged group of sets\n",
        parse_mode="HTML",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text

    if not text:
        return

    # Reject messages from non-authorized users
    if _authorized_user_id is not None and update.message.from_user.id != _authorized_user_id:
        logger.warning("Rejected message from unauthorized user %s", update.message.from_user.id)
        return

    state = _get_state(chat_id)
    state["messages"] = state.get("messages", [])[-10:] + [HumanMessage(content=text)]

    try:
        result = await agent_graph.ainvoke(state)
        _update_state(chat_id, result)

        response_text = result.get("response_text", "")
        if response_text:
            html = _md_to_html(response_text)
            try:
                await update.message.reply_text(html, parse_mode="HTML")
            except telegram.error.BadRequest:
                await update.message.reply_text(response_text)
    except Exception:
        logger.exception("Error processing message")
        await update.message.reply_text(
            "Something went wrong processing that. Please try again."
        )
