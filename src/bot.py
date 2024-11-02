import discord
from discord.ext import commands
from typing import Optional, Union
from .utils.logger import logger
from .config import config, Config
from src.utils.loader import ModuleLoader
from discord import Interaction
from discord.app_commands import AppCommandError, errors
from discord import app_commands
from src.utils.settings_manager import SettingsManager

class DiscordBot(commands.Bot):
    def __init__(self) -> None:
        intents: discord.Intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        # Get prefix from config, default to "!"
        prefix: str = config.get('command_prefix', '!')
        
        super().__init__(
            command_prefix=prefix,
            intents=intents,
            # Remove default help command since we're using our custom help
            help_command=None,
            # Add description for help command to use
            description=config.get('bot_description', 'A Discord Bot with custom commands.')
        )
        
        # Store config instance
        self.config: Config = config
        # Add settings manager instance
        self.settings: SettingsManager = SettingsManager()

    async def setup_hook(self) -> None:
        """Setup hook that runs after the bot logs in but before it connects to Discord"""
        logger.info("Loading extensions...")
        
        # Load all extensions through the module loader
        await ModuleLoader.load_modules(self)
        
        # Sync commands with Discord
        logger.info("Syncing commands...")
        await self.tree.sync()
        logger.info("Commands synced successfully!")
        
        self.tree.error(self.on_app_command_error)
    
    async def on_command_error(
        self, 
        ctx: commands.Context,
        error: commands.CommandError
    ) -> None:
        """Global error handler"""
        if isinstance(error, commands.CommandNotFound):
            return
            
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command!")
            return
            
        logger.exception(f"Unhandled exception in command {ctx.command}", exc_info=error)
    
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        """Handle slash command errors"""
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "❌ You don't have permission to use this command. Required permissions: " +
                ", ".join(error.missing_permissions),
                ephemeral=True
            )
            return
            
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"⏳ This command is on cooldown. Try again in {error.retry_after:.1f} seconds.",
                ephemeral=True
            )
            return
            
        if isinstance(error, app_commands.errors.CommandNotFound):
            await interaction.response.send_message(
                "❌ This command doesn't exist. Use `/help all` to see available commands.",
                ephemeral=True
            )
            return

        # Log unexpected errors
        logger.error(f"Command error in {interaction.command}: {str(error)}")
        await interaction.response.send_message(
            "❌ An unexpected error occurred. The bot administrator has been notified.",
            ephemeral=True
        )
