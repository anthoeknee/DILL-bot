import asyncio
import sys
from src.core.client import DiscordBot
from src.core.config import Settings
from src.utils.logger import logger


async def main():
    try:
        settings = Settings.get()
        bot = DiscordBot()

        logger.info("Starting bot...")
        await bot.start(settings.discord_token)

    except Exception as e:
        logger.error(f"Failed to start bot: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown initiated by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)
