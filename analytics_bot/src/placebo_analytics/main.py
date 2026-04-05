import logging

from langgraph.checkpoint.memory import MemorySaver
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from placebo_analytics import db
from placebo_analytics.agent.graph import init_graph
from placebo_analytics.config import settings
from placebo_analytics.scheduler import schedule_digest
from placebo_analytics.telegram_handler import handle_message, help_command, start_command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def post_init(app) -> None:
    await db.init_pool(settings.database_url)
    init_graph(checkpointer=MemorySaver())
    schedule_digest(app, settings.digest_day, settings.digest_hour, settings.digest_minute)
    logger.info("Analytics bot initialized — DB pool ready, graph compiled, digest scheduled.")


async def post_shutdown(app) -> None:
    await db.close_pool()
    logger.info("Analytics bot shut down — DB pool closed.")


def main() -> None:
    logger.info("Placebo analytics bot starting...")

    app = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
