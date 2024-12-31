# src/settings.py
import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands
from src.config import ConfigManager
from src.models import ServerConfig
from src.utils import is_discord_id, load_google_credentials, requires_configuration


class SettingsCog(commands.GroupCog, name="settings"):
    """Bot configuration and settings management"""

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.config_manager = bot.config_manager
        logging.info("SettingsCog initialized.")

    @app_commands.command(
        name="setup", description="Configure the bot's settings for this server"
    )
    @app_commands.describe(
        forum_channel="The forum channel to monitor",
        spreadsheet_id="The ID of the Google Spreadsheet (from the URL)",
        yes_emoji="Custom emoji for positive votes (optional)",
        no_emoji="Custom emoji for negative votes (optional)",
    )
    @commands.has_permissions(administrator=True)
    async def setup_command(
        self,
        interaction: discord.Interaction,
        forum_channel: discord.ForumChannel,
        spreadsheet_id: str,
        yes_emoji: Optional[str] = None,
        no_emoji: Optional[str] = None,
    ):
        """Comprehensive setup command that configures all necessary bot settings"""
        await interaction.response.defer()

        try:
            # Default emoji IDs if not provided
            yes_emoji_id = (
                "1263941895625900085"
                if not yes_emoji
                else yes_emoji.strip("<:>").split(":")[-1]
            )
            no_emoji_id = (
                "1263941842244730972"
                if not no_emoji
                else no_emoji.strip("<:>").split(":")[-1]
            )

            # Predefined tag IDs and names
            REQUIRED_TAGS = {
                "Not Added to List": 1258877875457626154,
                "Added to List": 1298038416025452585,
                "Initial Vote": 1315553680874803291,
            }

            # Verify all required tags exist in the forum channel
            existing_tags = {tag.id: tag for tag in forum_channel.available_tags}
            missing_tags = []
            for tag_name, tag_id in REQUIRED_TAGS.items():
                if tag_id not in existing_tags:
                    missing_tags.append(tag_name)

            if missing_tags:
                raise ValueError(
                    f"Missing required tags: {', '.join(missing_tags)}\nPlease ensure all required tags exist in the forum channel."
                )

            # Create/update server config
            config = ServerConfig(
                server_id=interaction.guild_id,
                forum_channel_id=str(forum_channel.id),
                spreadsheet_id=spreadsheet_id,
                yes_emoji_id=yes_emoji_id,
                no_emoji_id=no_emoji_id,
                enabled=True,  # Enable the bot by default when setting up
            )

            # Save the configuration
            self.config_manager.save_config(config)

            # Start the sync task if it's not running
            if (
                hasattr(self.bot, "sync_forum_data")
                and not self.bot.sync_forum_data.is_running()
            ):
                self.bot.sync_forum_data.start()

            # Create response embed
            embed = discord.Embed(
                title="✅ Bot Setup Complete",
                color=discord.Color.green(),
                description="The bot has been successfully configured!",
            )
            embed.add_field(
                name="Forum Channel", value=forum_channel.mention, inline=False
            )
            embed.add_field(
                name="Spreadsheet ID", value=f"`{spreadsheet_id}`", inline=False
            )
            embed.add_field(
                name="Required Tags",
                value="\n".join(f"• {tag_name}" for tag_name in REQUIRED_TAGS.keys()),
                inline=False,
            )
            embed.add_field(
                name="Vote Emojis",
                value=f"Yes: <:pickle_yes:{yes_emoji_id}>\nNo: <:pickle_no:{no_emoji_id}>",
                inline=False,
            )
            embed.set_footer(
                text="Use /status to check the bot's current configuration at any time."
            )

            await interaction.followup.send(embed=embed)

        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Setup Failed",
                color=discord.Color.red(),
                description=f"An error occurred during setup: {str(e)}",
            )
            await interaction.followup.send(embed=error_embed)
            logging.error(f"Setup failed: {e}", exc_info=True)

    @app_commands.command(
        name="status", description="Display current bot configuration and status"
    )
    async def status(self, interaction: discord.Interaction):
        """Comprehensive status command that shows all bot settings and current state"""
        await interaction.response.defer()

        try:
            config = self.config_manager.get_config(str(interaction.guild_id))
            if not config:
                await interaction.followup.send(
                    "Bot is not configured for this server. Use `/setup` to configure the bot."
                )
                return

            embed = discord.Embed(
                title="Bot Status & Configuration",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )

            # Basic Configuration
            embed.add_field(
                name="Basic Configuration",
                value=f"**Enabled:** {config.enabled}\n"
                f"**Configured:** {config.is_configured}\n"
                f"**Forum Channel:** <#{config.forum_channel_id}>\n"
                f"**Spreadsheet ID:** `{config.spreadsheet_id}`",
                inline=False,
            )

            # Emoji Configuration
            embed.add_field(
                name="Vote Emojis",
                value=f"**Yes:** <:pickle_yes:{config.yes_emoji_id}>\n"
                f"**No:** <:pickle_no:{config.no_emoji_id}>",
                inline=False,
            )

            # Background Tasks
            sync_task_running = (
                hasattr(self.bot, "sync_forum_data")
                and self.bot.sync_forum_data.is_running()
            )
            embed.add_field(
                name="Background Tasks",
                value=f"**Sync Task Running:** {sync_task_running}\n"
                f"**Last Sync:** {getattr(self.bot, 'last_sync_time', 'Never')}",
                inline=False,
            )

            # Exempt Threads
            exempt_threads = config.exempt_threads or {}
            exempt_count = len(exempt_threads)
            embed.add_field(
                name="Exempt Threads", value=f"**Count:** {exempt_count}", inline=False
            )

            embed.set_footer(text="Use /setup to modify these settings")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            error_embed = discord.Embed(
                title="❌ Error",
                color=discord.Color.red(),
                description=f"An error occurred while fetching status: {str(e)}",
            )
            await interaction.followup.send(embed=error_embed)
            logging.error(f"Status command failed: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    """
    Sets up the Settings cog and adds it to the bot.

    This function is called by the bot when loading extensions.
    """
    cog = SettingsCog(bot)
    await bot.add_cog(cog)
    logging.info("Settings cog loaded")
