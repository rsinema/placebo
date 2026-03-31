import logging

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from placebo_bot import db
from placebo_bot.config import settings
from placebo_bot.scheduler import schedule_checkin
from placebo_bot.telegram_handler import handle_message, help_command, start_command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def post_init(app) -> None:
    await db.init_pool(settings.database_url)
    schedule_checkin(app, settings.checkin_hour, settings.checkin_minute)
    logger.info("Bot initialized — DB pool ready, check-in scheduled.")


async def post_shutdown(app) -> None:
    await db.close_pool()
    logger.info("Bot shut down — DB pool closed.")


def main() -> None:
    logger.info("Placebo bot starting...")

    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
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
