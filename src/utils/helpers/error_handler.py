from typing import Dict, Type, Optional
import discord
from discord.ext import commands
from discord import app_commands
from src.utils.logging.logger import logger

class ErrorHandler:
    @staticmethod
    async def handle_error(ctx: commands.Context, error: commands.CommandError) -> None:
        """Centralized error handling for all commands"""
        
        # Dictionary mapping error types to user-friendly messages
        error_messages: Dict[Type[commands.CommandError], str] = {
            commands.MissingPermissions: "You don't have permission to use this command!",
            commands.MissingRequiredArgument: "Missing required argument: {error.param.name}",
            commands.BadArgument: "Invalid argument provided. Please check the command usage.",
            commands.CommandOnCooldown: "This command is on cooldown. Try again in {error.retry_after:.1f} seconds.",
            commands.NoPrivateMessage: "This command cannot be used in private messages.",
            commands.BotMissingPermissions: "I don't have the required permissions to execute this command!",
            app_commands.CheckFailure: "You don't have permission to use this command!",
            app_commands.NoPrivateMessage: "This command can only be used in servers",
            app_commands.MissingPermissions: "You need administrator permissions to use this command",
        }

        # Get original error if it's wrapped
        error = getattr(error, 'original', error)

        # Ignore CommandNotFound errors
        if isinstance(error, commands.CommandNotFound):
            return

        # Get the error message if it exists in our mapping
        error_type: Type[commands.CommandError] = type(error)
        if error_type in error_messages:
            message: str = error_messages[error_type]
            # Format the message if it contains error attributes
            if '{' in message:
                message = message.format(error=error)
            await ctx.send(message)
            return

        # Log unexpected errors
        command_name: Optional[str] = ctx.command.name if ctx.command else 'Unknown'
        logger.exception(
            f"Unhandled exception in command {command_name}",
            exc_info=error,
            extra={
                'command': command_name,
                'author': str(ctx.author),
                'channel': str(ctx.channel),
                'guild': str(ctx.guild) if ctx.guild else 'DM'
            }
        )
        
        # Send a generic error message to the user
        await ctx.send("An unexpected error occurred. Please try again later.")

    @staticmethod
    async def handle_app_command_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        """Handle errors from application commands (slash commands)"""
        
        # Get original error if it's wrapped
        error = getattr(error, 'original', error)
        
        try:
            if not interaction.response.is_done():
                if isinstance(error, app_commands.NoPrivateMessage):
                    await interaction.response.send_message(
                        "❌ This command can only be used in servers",
                        ephemeral=True
                    )
                elif isinstance(error, (app_commands.CheckFailure, app_commands.MissingPermissions)):
                    await interaction.response.send_message(
                        "❌ You don't have permission to use this command.",
                        ephemeral=True
                    )
                else:
                    logger.exception(
                        f"Unhandled exception in app command {interaction.command.name if interaction.command else 'Unknown'}",
                        exc_info=error
                    )
                    await interaction.response.send_message(
                        "An unexpected error occurred. Please try again later.",
                        ephemeral=True
                    )
        except discord.InteractionResponded:
            pass

async def setup(bot: commands.Bot) -> None:
    """Set up the error handler module."""
    bot.error_handler = ErrorHandler()
    
    @bot.event
    async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
        await bot.error_handler.handle_error(ctx, error)
        
    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError
    ) -> None:
        await bot.error_handler.handle_app_command_error(interaction, error)
