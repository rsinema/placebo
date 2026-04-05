import logging
import re
from datetime import datetime, timedelta

import telegram.error
from langchain_core.messages import HumanMessage
from telegram import Update
from telegram.ext import ContextTypes

from placebo_analytics.agent import graph as _graph
from placebo_analytics import db

logger = logging.getLogger(__name__)

# Simple rate limiting: count messages per chat_id in a sliding window
_rate_limit_store: dict[int, list[datetime]] = {}


def _check_rate_limit(chat_id: int, max_messages: int = 5, window_seconds: int = 10) -> bool:
    """Return True if user is within rate limit, False if they exceeded it."""
    now = datetime.now()
    cutoff = now - timedelta(seconds=window_seconds)
    if chat_id not in _rate_limit_store:
        _rate_limit_store[chat_id] = []
    _rate_limit_store[chat_id] = [t for t in _rate_limit_store[chat_id] if t > cutoff]
    if len(_rate_limit_store[chat_id]) >= max_messages:
        return False
    _rate_limit_store[chat_id].append(now)
    return True


def _md_to_html(text: str) -> str:
    """Convert basic Markdown bold to HTML for Telegram."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await db.set_bot_setting("analytics_chat_id", str(chat_id))
    await update.message.reply_text(
        "Welcome to Placebo Analytics! 📊\n\n"
        "I can answer analytical questions about your health data:\n"
        "• \"How has my sleep been trending?\"\n"
        "• \"What's the correlation between mood and energy?\"\n"
        "• \"How does this week compare to last week?\"\n"
        "• \"How consistent have I been with my metrics?\"\n"
        "• \"How effective has my experiment been?\"\n\n"
        "Type /help for more info."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "<b>Placebo Analytics — What I can do:</b>\n\n"
        "• Trend analysis — \"How has my energy been over the last 30 days?\"\n"
        "• Metric summary — \"Give me an overview of my sleep data\"\n"
        "• Correlation — \"Is there a correlation between my caffeine intake and sleep quality?\"\n"
        "• Experiment analysis — \"How effective has my no-screens-before-bed experiment been?\"\n"
        "• Multi-metric overview — \"Show me a summary of all my metrics this week\"\n"
        "• Period comparison — \"Compare this week to last week\"\n"
        "• Consistency / streak — \"How consistent have I been lately?\"\n"
        "• Correlation ranking — \"What are my strongest metric correlations?\"\n\n"
        "You also receive a weekly digest every Monday at 09:00 UTC.\n\n"
        "Type naturally — I'll figure out what you're asking for!",
        parse_mode="HTML",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    text = update.message.text

    if not text:
        return

    if not _check_rate_limit(chat_id):
        await update.message.reply_text("Whoa! Slow down a bit — max 5 messages every 10 seconds. 🐢")
        return

    config = {"configurable": {"thread_id": str(chat_id)}}
    inputs = {
        "messages": [HumanMessage(content=text)],
        "chat_id": chat_id,
    }

    try:
        result = await _graph.agent_graph.ainvoke(inputs, config=config)

        response_text = result.get("response_text", "")
        chart_bytes = result.get("chart_bytes")
        suggested_followups: list[str] = result.get("suggested_followups", [])

        if response_text:
            html = _md_to_html(response_text)
            try:
                await update.message.reply_text(html, parse_mode="HTML")
            except telegram.error.BadRequest:
                await update.message.reply_text(response_text)

        if chart_bytes:
            from io import BytesIO
            from telegram import InputFile
            bytes_io = BytesIO(chart_bytes)
            bytes_io.name = "chart.png"
            await update.message.reply_photo(photo=InputFile(bytes_io, filename="chart.png"))

        if suggested_followups:
            followup_text = "💡 " + "\n💡 ".join(suggested_followups)
            await update.message.reply_text(followup_text)

    except Exception:
        logger.exception("Error processing analytics message")
        await update.message.reply_text(
            "I had trouble analyzing that. Try rephrasing? 😅"
        )
