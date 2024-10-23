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
            # Check if user is owner despite missing admin perms
            if interaction.user.id == self.config.get('owner_id'):
                try:
                    # Get the command name
                    command_name = interaction.command.name
                    
                    # Get command options based on the specific command
                    kwargs = {}
                    if command_name == "setup_forum_tracker":
                        for name in ['forum_channel', 'spreadsheet_id']:
                            if hasattr(interaction.namespace, name):
                                kwargs[name] = getattr(interaction.namespace, name)
                    elif command_name in ["set", "get", "delete"]:
                        for name in ['key', 'value']:
                            if hasattr(interaction.namespace, name):
                                kwargs[name] = getattr(interaction.namespace, name)
                    
                    # Get the cog instance
                    cog = interaction.command.binding
                    
                    # Call the command
                    await interaction.command.callback(
                        cog,
                        interaction,
                        **kwargs
                    )
                    return
                except Exception as e:
                    logger.error(f"Error executing command: {str(e)}")
                    await interaction.response.send_message(
                        f"Error executing command: {str(e)}",
                        ephemeral=True
                    )
                    return
            else:
                await interaction.response.send_message(
                    "You need administrator permissions to use this command.",
                    ephemeral=True
                )
                return
        
        # Handle other errors
        await interaction.response.send_message(
            f"An error occurred: {str(error)}",
            ephemeral=True
        )
