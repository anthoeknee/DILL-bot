import discord
from discord.ext import commands
from src.utils.logger import logger

async def setup(bot: commands.Bot) -> None:
    """Sets up the on_ready event"""
    @bot.event
    async def on_ready() -> None:
        """Event triggered when bot is ready"""
        logger.info(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
        logger.info(f"Connected to {len(bot.guilds)} guilds")
        
        # Debug registered commands
        logger.info("Registered Slash Commands:")
        for cmd in bot.tree.get_commands():
            logger.info(f"- /{cmd.name}")
        
        logger.info("Registered Prefix Commands:")
        for cmd in bot.commands:
            logger.info(f"- {bot.command_prefix}{cmd.name}")
        
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
