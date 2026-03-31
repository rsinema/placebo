import logging
import re

import telegram.error
from langchain_core.messages import HumanMessage
from telegram import Update
from telegram.ext import ContextTypes

from placebo_bot.agent.graph import agent_graph
from placebo_bot import db

logger = logging.getLogger(__name__)

# In-memory state store keyed by chat_id
_state_store: dict[int, dict] = {}


def _get_state(chat_id: int) -> dict:
    if chat_id not in _state_store:
        _state_store[chat_id] = {
            "messages": [],
            "intent": "",
            "chat_id": chat_id,
            "checkin_active": False,
            "checkin_metrics": [],
            "checkin_current_index": 0,
            "checkin_responses": [],
            "pending_metric": None,
            "response_text": "",
        }
    return _state_store[chat_id]


def _md_to_html(text: str) -> str:
    """Convert basic Markdown bold to HTML for Telegram."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def _update_state(chat_id: int, result: dict) -> None:
    state = _state_store.setdefault(chat_id, {})
    state.update(result)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await db.set_bot_setting("chat_id", str(chat_id))
    _get_state(chat_id)  # initialize state
    await update.message.reply_text(
        "Welcome to Placebo! I'm your health tracking assistant.\n\n"
        "I'll send you daily check-ins to track your metrics. You can also:\n"
        "• Say 'start check-in' to begin one now\n"
        "• Say 'add metric for [something]' to add a new metric\n"
        "• Say 'show metrics' to see what you're tracking\n"
        "• Say 'start experiment: [name]' to begin an experiment\n"
        "• Say 'show experiments' to see your experiments\n\n"
        "Type /help for more info."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Commands &amp; phrases I understand:</b>\n\n"
        "• start check-in — begin a check-in now\n"
        "• skip today — skip the current check-in\n"
        "• add metric for [description] — add a new metric\n"
        "• remove metric [name] — archive a metric\n"
        "• show metrics — list active metrics\n"
        "• start experiment: [name] — start a new experiment\n"
        "• end experiment: [name] — end an experiment\n"
        "• show experiments — list all experiments\n"
        "• set check-in to HH:MM — change check-in time\n\n"
        "During check-ins, just respond naturally — I'll parse your answers.",
        parse_mode="HTML",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text

    if not text:
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


async def trigger_checkin(chat_id: int, send_fn) -> None:
    """Trigger a check-in programmatically (called by scheduler)."""
    from placebo_bot.agent.nodes import start_checkin as _start_checkin

    state = _get_state(chat_id)
    result = await _start_checkin(state)
    _update_state(chat_id, result)

    response_text = result.get("response_text", "")
    if response_text:
        await send_fn(chat_id, response_text)
