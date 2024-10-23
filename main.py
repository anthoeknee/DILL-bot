import asyncio
from typing import Optional
from src.bot import DiscordBot
from src.utils.logging.logger import logger  # Fix this import path
from src.config import config

async def main() -> None:
    """Main entry point for the bot"""
    token: Optional[str] = config.token
    
    if not token:
        logger.critical("No Discord token found in configuration!")
        return
        
    try:
        bot: DiscordBot = DiscordBot()
        logger.info("Starting bot...")
        await bot.start(token)
    except Exception as e:
        logger.exception("Fatal error occurred", exc_info=e)
    finally:
        logger.info("Shutting down...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot shutdown by user")
