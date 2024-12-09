import discord
from discord.ext import commands
from typing import Optional

from src.core.config import Settings
from src.core.feature_manager import FeatureManager
from src.core.database import init_db
from src.utils.logger import logger


class DiscordBot(commands.Bot):
    def __init__(self):
        self.settings = Settings.get()

        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix=self.settings.command_prefix,
            intents=intents,
            owner_id=self.settings.owner_id,
        )

        self.feature_manager: Optional[FeatureManager] = None

    async def setup_hook(self) -> None:
        """Initialize bot components before connecting to Discord"""
        logger.info("Initializing bot components...")

        # Initialize database
        init_db()
        logger.info("Database initialized")

        # Initialize and load features
        self.feature_manager = FeatureManager(self)
        await self.feature_manager.load_all_features()

        logger.info("Bot setup completed successfully")

    async def on_ready(self):
        """Called when the bot has successfully connected to Discord"""
        logger.info(f"Logged in as {self.user.name} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guilds")

        # Set bot presence
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=f"{self.settings.command_prefix}help",
            )
        )

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Global error handler for command errors"""
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
            return

        if isinstance(error, commands.CheckFailure):
            return  # Handled by individual checks

        # Log unexpected errors
        logger.error(f"Command error in {ctx.command}: {str(error)}")
        await ctx.send("An error occurred while executing the command.")
