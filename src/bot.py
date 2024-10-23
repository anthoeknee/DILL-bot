import discord
from discord.ext import commands
from typing import Optional, Union
from .utils.logging.logger import logger  # Changed from .utils.logger
from .config import config, Config
from .utils.helpers.loader import ModuleLoader
from .utils.helpers.error_handler import ErrorHandler

class DiscordBot(commands.Bot):
    def __init__(self) -> None:
        intents: discord.Intents = discord.Intents.default()
        intents.message_content = True  # This is the key intent for reading messages
        intents.members = True
        intents.dm_messages = True
        intents.dm_typing = True  # Add this
        intents.guild_messages = True  # Add this
        
        # Get prefix from config, default to "!"
        prefix: str = config.get('command_prefix', '!')
        
        super().__init__(
            command_prefix=prefix,
            intents=intents,
            help_command=None
        )
        
        # Store config instance
        self.config: Config = config
        
    async def setup_hook(self) -> None:
        """Setup hook that runs after the bot logs in but before it connects to Discord"""
        logger.info("Initializing services...")
        await ModuleLoader.load_services(self)
        
        logger.info("Loading extensions...")
        await ModuleLoader.load_modules(self)
    
    async def on_command_error(
        self, 
        ctx: commands.Context,
        error: commands.CommandError
    ) -> None:
        """Global error handler"""
        await ErrorHandler.handle_error(ctx, error)
