import discord
from discord.ext import commands
from src.utils.logging.logger import logger  # Fix this import path
from src.utils.helpers.sync import CommandSyncManager

async def setup(bot: commands.Bot) -> None:
    """Sets up the on_ready event"""
    @bot.event
    async def on_ready() -> None:
        """Event triggered when bot is ready"""
        logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
        logger.info(f"Connected to {len(bot.guilds)} guilds")
        
        # Check and sync commands if needed - Do this BEFORE setting presence
        sync_manager = CommandSyncManager(bot)
        try:
            # Force sync on startup instead of checking
            synced = await sync_manager.sync_commands()
            logger.info(f"Synced {len(synced)} commands on startup")
        except Exception as e:
            logger.error(f"Failed to sync commands on startup: {e}", exc_info=True)
        
        # Set custom status from config
        status_text: str = bot.config.get('status_text', 'your commands')
        status_type: discord.ActivityType = getattr(
            discord.ActivityType, 
            bot.config.get('status_type', 'watching').lower()
        )
        
        await bot.change_presence(
            activity=discord.Activity(
                type=status_type,
                name=status_text
            )
        )
