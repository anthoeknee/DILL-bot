# src/settings.py
import logging

import discord
from discord.ext import commands

from src.config import ConfigManager
from src.models import ServerConfig
from src.utils import is_discord_id, load_google_credentials, requires_configuration


class SettingsCog(commands.Cog):
    """Cog for server-specific settings commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        logging.info("SettingsCog initialized.")

    async def is_allowed_user(self, ctx: commands.Context) -> bool:
        """Checks if the user is the bot owner or the specified user ID."""
        return (
            await self.bot.is_owner(ctx.author)
            or str(ctx.author.id) == "1114624963169747068"
        )

    @commands.command(name="config")
    async def config(self, ctx: commands.Context):
        """Configures the bot for the server."""
        if not await self.is_allowed_user(ctx):
            await ctx.send("You do not have permission to use this command.")
            return
        logging.info(f"Configuration command triggered by {ctx.author} in {ctx.guild}.")
        session = self.bot.session  # Get the session from the bot
        config_manager = ConfigManager(session)
        try:
            config = config_manager.get_config(ctx.guild.id)
            if config:
                await ctx.send(
                    "Bot is already configured for this server. Use `!reset` to reset the configuration."
                )
                return

            config = ServerConfig(server_id=str(ctx.guild.id))
            session.add(config)
            session.commit()
            await ctx.send(
                "Bot configured for this server. Use `!set_channel`, `!set_role`, and `!set_credentials` to set up the bot."
            )
        except Exception as e:
            logging.error(f"Error during configuration: {e}")
            await ctx.send("An error occurred while configuring the bot.")

    @commands.command(name="reset")
    async def reset(self, ctx: commands.Context):
        """Resets the bot configuration for the server."""
        if not await self.is_allowed_user(ctx):
            await ctx.send("You do not have permission to use this command.")
            return
        logging.info(f"Reset command triggered by {ctx.author} in {ctx.guild}.")
        session = self.bot.session  # Get the session from the bot
        config_manager = ConfigManager(session)
        try:
            config = config_manager.get_config(ctx.guild.id)
            if not config:
                await ctx.send("Bot is not configured for this server.")
                return

            session.delete(config)
            session.commit()
            await ctx.send("Bot configuration reset for this server.")
        except Exception as e:
            logging.error(f"Error during reset: {e}")
            await ctx.send("An error occurred while resetting the configuration.")
