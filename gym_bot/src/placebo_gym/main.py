import logging

from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from placebo_gym import db
from placebo_gym.config import settings
from placebo_gym.telegram_handler import handle_message, help_command, start_command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def post_init(app) -> None:
    await db.init_pool(settings.database_url)
    logger.info("Gym bot initialized — DB pool ready.")


async def post_shutdown(app) -> None:
    await db.close_pool()
    logger.info("Gym bot shut down — DB pool closed.")


def main() -> None:
    logger.info("Placebo gym bot starting...")

    app = (
        ApplicationBuilder()
        .token(settings.gym_telegram_bot_token)
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
