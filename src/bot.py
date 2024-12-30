# src/bot.py
import json
import discord
from discord.ext import commands, tasks
from src.config import load_config, ConfigManager
from src.settings import SettingsCog
from src.utils import requires_configuration
from src.spreadsheets import SpreadsheetService
import logging
import os
from discord import ui
from sqlalchemy.orm import Session

# Load configuration
config = load_config()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class CredentialsModal(ui.Modal, title="Set Google Credentials"):
    credentials = ui.TextInput(
        label="Google Credentials JSON", style=discord.TextStyle.paragraph
    )

    def __init__(self, bot, server_id):
        super().__init__()
        self.bot = bot
        self.server_id = server_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            credentials = self.credentials.value
            await self.bot.set_credentials(self.server_id, credentials)
            await interaction.response.send_message(
                "Google credentials set successfully.", ephemeral=True
            )
        except Exception as e:
            logging.error(f"Error setting google credentials: {e}")
            await interaction.response.send_message(
                f"Error setting google credentials: {e}", ephemeral=True
            )


class DiscordBot:
    def __init__(
        self,
        base_bot: commands.Bot,
        config_manager: ConfigManager,
        session: Session,
    ):
        self.bot = base_bot
        self.session = session
        self.config_manager = config_manager
        self.spreadsheet_service = SpreadsheetService(self.session, self)
        self.sync_guild_id = int(os.getenv("SYNC_GUILD_ID"))
        self.background_task_running = False
        logging.info("DiscordBot initialized.")

    async def on_ready(self):
        logging.info(f"Logged in as {self.bot.user.name}")
        await self.check_and_initialize()

    async def setup_hook(self):
        logging.info("Setting up bot commands and cogs.")
        await self._register_commands()
        await self.bot.add_cog(SettingsCog(self))
        await self.check_and_initialize()

    async def check_and_initialize(self):
        server_config = self.config_manager.get_config(self.sync_guild_id)
        if server_config and server_config.is_configured:
            logging.info(
                "Bot is configured, initializing SpreadsheetService and starting background task."
            )
            await self.spreadsheet_service.initialize_google_api()
            self.sync_thread_tags.start()
            self.background_task_running = True
        else:
            logging.info(
                "Bot is not configured, skipping SpreadsheetService initialization and background task."
            )

    async def close(self):
        logging.info("Closing bot and database session.")
        if self.background_task_running:
            self.sync_thread_tags.cancel()
        self.session.close()
        await super().close()

    async def sync_all_threads(self, ctx):
        logging.info(f"Syncing all threads for server {ctx.guild.id}.")
        await self.spreadsheet_service.sync_all_threads(ctx)

    async def _register_commands(self):
        logging.info("Registering bot commands as slash commands.")
        for command in self.commands:
            if not command.name == "help":
                self.tree.command(
                    name=command.name,
                    description=command.help or "No description provided",
                )(command.callback)
        await self.tree.sync()

    async def _initialize_default_config(self):
        logging.info("Initializing default configuration if none exists.")
        if not self.sync_guild_id:
            logging.warning(
                "SYNC_GUILD_ID is not set, skipping default config initialization."
            )
            return
        config = self.config_manager.get_config()
        if not config:
            spreadsheet_id = os.getenv("DEFAULT_SPREADSHEET_ID")
            if not spreadsheet_id:
                logging.warning(
                    "DEFAULT_SPREADSHEET_ID is not set, skipping default config initialization."
                )
                return
            logging.info(
                f"Creating default config for server {self.sync_guild_id} with spreadsheet ID {spreadsheet_id}."
            )
            self.config_manager.create_or_update_config(
                {"server_id": self.sync_guild_id, "spreadsheet_id": spreadsheet_id}
            )
            logging.info(
                f"Default config created for server {self.sync_guild_id} with spreadsheet ID {spreadsheet_id}."
            )
        else:
            logging.info(
                f"Config already exists for server {self.sync_guild_id}, skipping default config initialization."
            )

    @commands.command(name="sync", help="Sync all threads with the spreadsheet.")
    @requires_configuration()
    async def sync_command(self, ctx):
        await self.sync_all_threads(ctx)

    @commands.command(name="setup", help="Setup the bot for this server.")
    async def setup_command(self, ctx):
        logging.info(f"Setting up bot for server {ctx.guild.id}.")
        await self._initialize_default_config()
        await ctx.send(
            "Bot setup complete. Please set the forum channel and google credentials."
        )

    @commands.command(name="set_spreadsheet", help="Set the spreadsheet ID.")
    @requires_configuration()
    async def set_spreadsheet(self, ctx, spreadsheet_id: str):
        logging.info(
            f"Setting spreadsheet ID to {spreadsheet_id} for server {ctx.guild.id}."
        )
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "spreadsheet_id": spreadsheet_id}
        )
        await ctx.send(f"Spreadsheet ID set to {spreadsheet_id}.")

    @commands.command(name="status", help="Get the bot status.")
    @requires_configuration()
    async def status_command(self, ctx):
        logging.info(f"Getting bot status for server {ctx.guild.id}.")
        config = self.config_manager.get_config(str(ctx.guild.id))
        if config:
            status = f"Bot is configured: {config.is_configured}\n"
            status += f"Spreadsheet ID: {config.spreadsheet_id}\n"
            status += f"Forum Channel ID: {config.forum_channel_id}\n"
            status += f"Enabled: {config.enabled}\n"
            await ctx.send(status)
        else:
            await ctx.send("Bot is not configured for this server.")

    @commands.command(name="enable", help="Enable the bot for this server.")
    @requires_configuration()
    async def enable(self, ctx):
        logging.info(f"Enabling bot for server {ctx.guild.id}.")
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "enabled": True}
        )
        await ctx.send("Bot enabled.")

    @commands.command(name="disable", help="Disable the bot for this server.")
    @requires_configuration()
    async def disable(self, ctx):
        logging.info(f"Disabling bot for server {ctx.guild.id}.")
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "enabled": False}
        )
        await ctx.send("Bot disabled.")

    @commands.command(name="exempt_thread", help="Exempt a thread from tag syncing.")
    @requires_configuration()
    async def exempt_thread(self, ctx, thread_id: str):
        logging.info(f"Exempting thread {thread_id} for server {ctx.guild.id}.")
        config = self.config_manager.get_config(str(ctx.guild.id))
        exempt_threads = config.exempt_threads or {}
        exempt_threads[thread_id] = True
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "exempt_threads": exempt_threads}
        )
        await ctx.send(f"Thread {thread_id} exempted.")

    @commands.command(
        name="unexempt_thread", help="Unexempt a thread from tag syncing."
    )
    @requires_configuration()
    async def unexempt_thread(self, ctx, thread_id: str):
        logging.info(f"Unexempting thread {thread_id} for server {ctx.guild.id}.")
        config = self.config_manager.get_config(str(ctx.guild.id))
        exempt_threads = config.exempt_threads or {}
        exempt_threads.pop(thread_id, None)
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "exempt_threads": exempt_threads}
        )
        await ctx.send(f"Thread {thread_id} unexempted.")

    @commands.command(name="exempt_channel", help="Exempt a channel from tag syncing.")
    @requires_configuration()
    async def exempt_channel(self, ctx, channel_id: str):
        logging.info(f"Exempting channel {channel_id} for server {ctx.guild.id}.")
        config = self.config_manager.get_config(str(ctx.guild.id))
        exempt_channels = config.exempt_channels or {}
        exempt_channels[channel_id] = True
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "exempt_channels": exempt_channels}
        )
        await ctx.send(f"Channel {channel_id} exempted.")

    @commands.command(
        name="unexempt_channel", help="Unexempt a channel from tag syncing."
    )
    @requires_configuration()
    async def unexempt_channel(self, ctx, channel_id: str):
        logging.info(f"Unexempting channel {channel_id} for server {ctx.guild.id}.")
        config = self.config_manager.get_config(str(ctx.guild.id))
        exempt_channels = config.exempt_channels or {}
        exempt_channels.pop(channel_id, None)
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "exempt_channels": exempt_channels}
        )
        await ctx.send(f"Channel {channel_id} unexempted.")

    @commands.command(name="channel", help="Set the forum channel ID.")
    @requires_configuration()
    async def channel(self, ctx, channel_id: str):
        logging.info(
            f"Setting forum channel ID to {channel_id} for server {ctx.guild.id}."
        )
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "forum_channel_id": channel_id}
        )
        await ctx.send(f"Forum channel ID set to {channel_id}.")

    @commands.command(name="set_credentials", help="Set the google credentials.")
    @requires_configuration()
    async def set_credentials_command(self, ctx):
        logging.info(f"Opening credentials modal for server {ctx.guild.id}.")
        modal = CredentialsModal(self, str(ctx.guild.id))
        await ctx.interaction.response.send_modal(modal)

    async def set_credentials(self, server_id: str, credentials: str):
        logging.info(f"Setting google credentials for server {server_id}.")
        self.config_manager.set_google_credentials(server_id, json.loads(credentials))
        await self.spreadsheet_service.initialize_google_api(server_id)

    @tasks.loop(minutes=30)
    async def sync_thread_tags(self):
        logging.info("Running sync_thread_tags background task.")
        if self.sync_guild_id:
            guild = self.get_guild(int(self.sync_guild_id))
            if guild:
                await self.spreadsheet_service.sync_all_threads(guild)
            else:
                logging.error(f"Guild with ID {self.sync_guild_id} not found.")
        else:
            logging.warning("SYNC_GUILD_ID is not set, skipping background task.")
