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
        finally:
            session.close()

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
        finally:
            session.close()

    @commands.command(name="set_channel")
    @requires_configuration()
    async def set_channel(self, ctx: commands.Context, channel_id: str):
        """Sets the channel for bot messages."""
        if not await self.is_allowed_user(ctx):
            await ctx.send("You do not have permission to use this command.")
            return
        logging.info(
            f"Set channel command triggered by {ctx.author} in {ctx.guild} for channel {channel_id}."
        )
        session = self.bot.session  # Get the session from the bot
        config_manager = ConfigManager(session)
        try:
            is_valid, id_type = await is_discord_id(self.bot, channel_id)
            if not is_valid or id_type != "channel":
                await ctx.send("Invalid channel ID.")
                return

            config_manager.update_config(ctx.guild.id, channel_id=channel_id)
            await ctx.send(f"Channel updated to {channel_id}.")
        except Exception as e:
            logging.error(f"Error updating channel: {e}")
            await ctx.send("An error occurred while updating the channel.")
        finally:
            session.close()

    @commands.command(name="set_role")
    @requires_configuration()
    async def set_role(self, ctx: commands.Context, role_id: str):
        """Sets the role allowed to use the bot."""
        if not await self.is_allowed_user(ctx):
            await ctx.send("You do not have permission to use this command.")
            return
        logging.info(
            f"Set role command triggered by {ctx.author} in {ctx.guild} for role {role_id}."
        )
        session = self.bot.session  # Get the session from the bot
        config_manager = ConfigManager(session)
        try:
            is_valid, id_type = await is_discord_id(self.bot, role_id)
            if not is_valid or id_type != "role":
                await ctx.send("Invalid role ID.")
                return

            config_manager.update_config(ctx.guild.id, allowed_role_id=role_id)
            await ctx.send(f"Role updated to {role_id}.")
        except Exception as e:
            logging.error(f"Error updating role: {e}")
            await ctx.send("An error occurred while updating the role.")
        finally:
            session.close()

    @commands.command(name="set_credentials")
    @requires_configuration()
    async def set_credentials(self, ctx: commands.Context, *, credentials_json: str):
        """Sets the Google credentials for the bot."""
        if not await self.is_allowed_user(ctx):
            await ctx.send("You do not have permission to use this command.")
            return
        logging.info(
            f"Set credentials command triggered by {ctx.author} in {ctx.guild}."
        )
        session = self.bot.session  # Get the session from the bot
        config_manager = ConfigManager(session)
        try:
            load_google_credentials(credentials_json)
            config_manager.update_config(
                ctx.guild.id, google_credentials_json=credentials_json
            )
            await ctx.send("Credentials updated.")
        except Exception as e:
            logging.error(f"Error updating credentials: {e}")
            await ctx.send("An error occurred while updating the credentials.")
        finally:
            session.close()

    @commands.command(name="show_config")
    @requires_configuration()
    async def show_config(self, ctx: commands.Context):
        """Shows the current configuration for the server."""
        logging.info(f"Show config command triggered by {ctx.author} in {ctx.guild}.")
        session = self.bot.session  # Get the session from the bot
        config_manager = ConfigManager(session)
        try:
            config = config_manager.get_config(ctx.guild.id)
            if not config:
                await ctx.send("Bot is not configured for this server.")
                return

            embed = discord.Embed(title="Bot Configuration", color=0x3498DB)
            embed.add_field(name="Server ID", value=config.server_id, inline=False)
            embed.add_field(name="Channel ID", value=config.channel_id, inline=False)
            embed.add_field(
                name="Allowed Role ID", value=config.allowed_role_id, inline=False
            )
            await ctx.send(embed=embed)
        except Exception as e:
            logging.error(f"Error showing configuration: {e}")
            await ctx.send("An error occurred while showing the configuration.")
        finally:
            session.close()

    @commands.command(name="help")
    async def help(self, ctx: commands.Context):
        """Shows the help message for the bot."""
        logging.info(f"Help command triggered by {ctx.author} in {ctx.guild}.")
        embed = discord.Embed(
            title="Bot Help",
            description="Here are the available commands for the bot:",
            color=0x3498DB,
        )
        embed.add_field(
            name="!config",
            value="Configures the bot for the server. (Admin only)",
            inline=False,
        )
        embed.add_field(
            name="!reset",
            value="Resets the bot configuration for the server. (Admin only)",
            inline=False,
        )
        embed.add_field(
            name="!set_channel <channel_id>",
            value="Sets the channel for bot messages. (Admin only)",
            inline=False,
        )
        embed.add_field(
            name="!set_role <role_id>",
            value="Sets the role allowed to use the bot. (Admin only)",
            inline=False,
        )
        embed.add_field(
            name="!set_credentials <credentials_json>",
            value="Sets the Google credentials for the bot. (Admin only)",
            inline=False,
        )
        embed.add_field(
            name="!show_config",
            value="Shows the current configuration for the server.",
            inline=False,
        )
        embed.add_field(
            name="!chat <message>", value="Chats with the bot.", inline=False
        )
        embed.add_field(name="!help", value="Shows this help message.", inline=False)
        await ctx.send(embed=embed)
