# src/bot.py
import json
import discord
from discord.ext import commands, tasks
from src.config import load_config, ConfigManager
from src.utils import requires_configuration
from src.spreadsheets import SpreadsheetService
import logging
import os
from discord import ui
from sqlalchemy.orm import Session
from src.help import HelpCommand
from typing import Optional, Dict, Set
from src.settings import SettingsCog
from src.models import ServerConfig
from discord import app_commands


class DiscordBot(commands.Cog, name="Bot Management"):
    """Main bot functionality for spreadsheet synchronization and thread management"""

    def __init__(
        self,
        base_bot: commands.Bot,
        config_manager: ConfigManager,
        session: Session,
    ):
        super().__init__()
        self.bot = base_bot
        self.session = session
        self.config_manager = config_manager
        self.spreadsheet_service = SpreadsheetService(self.session, base_bot)
        self.sync_guild_id = int(os.getenv("SYNC_GUILD_ID", "0"))
        self.background_task_running = False
        logging.info("DiscordBot initialized.")
        logging.info(f"Commands registered: {[cmd.name for cmd in self.bot.commands]}")
        # Start the background task
        self.combined_sync_task.start()

    @commands.Cog.listener()
    async def on_ready(self):
        """Event handler for when the bot is ready"""
        try:
            logging.info(f"Logged in as {self.bot.user.name}")
            logging.info("Bot is ready!")
        except Exception as e:
            logging.error(f"Error in on_ready: {e}")

    @app_commands.command(
        name="sync", description="Synchronize all threads with the spreadsheet"
    )
    async def sync_slash_command(self, interaction: discord.Interaction):
        """Synchronize all threads in the forum channel with the Google Spreadsheet."""
        if not (
            interaction.user.guild_permissions.administrator
            or await self.bot.is_owner(interaction.user)
        ):
            await interaction.response.send_message(
                "You must be an administrator or the bot owner to use this command.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()
        progress_message = await interaction.followup.send(
            "Starting synchronization..."
        )

        try:
            guild = interaction.guild
            channel = guild.get_channel(
                int(self.config_manager.get_config(str(guild.id)).forum_channel_id)
            )

            if isinstance(channel, discord.ForumChannel):
                threads = [thread for thread in channel.threads if not thread.archived]
                updated_count = 0

                for thread in threads:
                    try:
                        thread_age = (
                            discord.utils.utcnow() - thread.created_at
                        ).total_seconds() / 3600
                        first_message = await thread.fetch_message(thread.id)

                        if first_message:
                            # Count reactions
                            yes_count = no_count = 0
                            for reaction in first_message.reactions:
                                if isinstance(reaction.emoji, discord.Emoji):
                                    if reaction.emoji.id == int(
                                        self.config_manager.get_config(
                                            str(guild.id)
                                        ).yes_emoji_id
                                    ):
                                        yes_count = reaction.count - 1
                                    elif reaction.emoji.id == int(
                                        self.config_manager.get_config(
                                            str(guild.id)
                                        ).no_emoji_id
                                    ):
                                        no_count = reaction.count - 1

                            total_votes = yes_count + no_count
                            vote_percentage = (
                                (yes_count / total_votes * 100)
                                if total_votes > 0
                                else 0
                            )

                            # Use the helper function to manage tags
                            if await self.manage_thread_tags(
                                thread, channel, vote_percentage, thread_age
                            ):
                                updated_count += 1

                    except Exception as e:
                        logging.error(f"Error processing thread {thread.id}: {e}")
                        continue

                await progress_message.edit(
                    content=f"Updated tags for {updated_count} threads. Starting spreadsheet sync..."
                )

            # Now sync with spreadsheet
            result = await self.spreadsheet_service.sync_all_threads(
                guild, progress_message
            )
            await progress_message.edit(content=f"{result}")

        except Exception as e:
            logging.error(f"Error in sync command: {e}", exc_info=True)
            await progress_message.edit(
                content=f"❌ An error occurred during synchronization: {str(e)}"
            )

    @commands.command(
        name="sync",
        help="Synchronize all threads with the spreadsheet",
        brief="Sync threads with spreadsheet",
    )
    @requires_configuration()
    async def sync_command(self, ctx):
        """Legacy sync command using prefix"""
        await self.sync_all_threads(ctx)
        await ctx.send("Synchronization complete!")

    @commands.command(
        name="enable",
        help="Enable bot functionality for this server",
        brief="Enable bot",
    )
    @requires_configuration()
    async def enable(self, ctx):
        """Enable the bot's functionality for this server"""
        logging.info(f"enable called by {ctx.author} in {ctx.guild}")
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "enabled": True}
        )
        await ctx.send("Bot enabled.")

    @commands.command(
        name="disable",
        help="Disable bot functionality for this server",
        brief="Disable bot",
    )
    @requires_configuration()
    async def disable(self, ctx):
        """Disable the bot's functionality for this server"""
        logging.info(f"disable called by {ctx.author} in {ctx.guild}")
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "enabled": False}
        )
        await ctx.send("Bot disabled.")

    @commands.command(
        name="exempt_thread",
        help="Exclude a thread from synchronization",
        brief="Exempt thread from sync",
        usage="<thread_id>",
    )
    @requires_configuration()
    async def exempt_thread(self, ctx, thread_id: str):
        """
        Exempt a specific thread from synchronization.
        """
        logging.info(f"Exempting thread {thread_id} for server {ctx.guild.id}")
        config = self.config_manager.get_config(str(ctx.guild.id))
        exempt_threads = config.exempt_threads or {}
        exempt_threads[thread_id] = True
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "exempt_threads": exempt_threads}
        )
        await ctx.send(f"Thread {thread_id} exempted.")

    @commands.command(
        name="unexempt_thread",
        help="Include a previously exempted thread in synchronization",
        brief="Remove thread exemption",
        usage="<thread_id>",
    )
    @requires_configuration()
    async def unexempt_thread(self, ctx, thread_id: str):
        """
        Remove the exemption status from a thread.
        """
        config = self.config_manager.get_config(str(ctx.guild.id))
        exempt_threads = config.exempt_threads or {}
        exempt_threads.pop(thread_id, None)
        self.config_manager.create_or_update_config(
            {"server_id": str(ctx.guild.id), "exempt_threads": exempt_threads}
        )
        await ctx.send(f"Thread {thread_id} unexempted.")

    @commands.command(
        name="fix_threads",
        help="Fix all thread tags and reactions in a forum channel",
        brief="Fix thread tags",
        usage="<channel_id>",
    )
    async def fix_threads(self, ctx, channel_id: str):
        """
        Fix all thread tags and reactions in the specified forum channel.
        Only usable by the bot owner or server owner.
        """
        logging.info(f"fix_threads called by {ctx.author} in {ctx.guild}")

        try:
            # Convert channel_id to integer
            try:
                channel_id_int = int(channel_id)
            except ValueError:
                logging.error(
                    f"Invalid channel ID format: {channel_id}. Expecting an integer."
                )
                await ctx.send(
                    f"Invalid channel ID format: {channel_id}. Please provide a valid channel ID."
                )
                return

            channel = self.bot.get_channel(channel_id_int)
            if not isinstance(channel, discord.ForumChannel):
                logging.warning(f"Invalid channel type for ID {channel_id}")
                await ctx.send("The provided channel ID must be a forum channel.")
                return

            # Get the available tags from the forum channel
            not_added_tag = None
            added_tag = None
            initial_vote_tag = None

            for tag in channel.available_tags:
                if tag.id == 1258877875457626154:
                    not_added_tag = tag
                elif tag.id == 1298038416025452585:
                    added_tag = tag
                elif tag.id == 1315553680874803291:
                    initial_vote_tag = tag

            if not all([not_added_tag, added_tag, initial_vote_tag]):
                await ctx.send("Could not find all required tags in the forum channel.")
                return

            status_message = await ctx.send("Starting thread fix process...")
            fixed_count = 0
            error_count = 0

            # Get all active threads in the channel
            threads = [thread for thread in channel.threads if not thread.archived]
            logging.info(f"Found {len(threads)} active threads to process")

            for thread in threads:
                try:
                    logging.info(f"Processing thread: {thread.id}")
                    # Get thread age in hours
                    thread_age = (
                        discord.utils.utcnow() - thread.created_at
                    ).total_seconds() / 3600
                    logging.info(f"Thread age: {thread_age} hours")

                    # Get the first message for reaction counting
                    first_message = await thread.fetch_message(thread.id)
                    logging.info(
                        f"Retrieved first message: {first_message.id if first_message else 'None'}"
                    )

                    # Count reactions
                    yes_reactions = 0
                    no_reactions = 0
                    if first_message:
                        for reaction in first_message.reactions:
                            if isinstance(reaction.emoji, discord.Emoji):
                                if (
                                    reaction.emoji.id == 1263941895625900085
                                ):  # pickle_yes
                                    yes_reactions = reaction.count - 1
                                elif (
                                    reaction.emoji.id == 1263941842244730972
                                ):  # pickle_no
                                    no_reactions = reaction.count - 1

                    logging.info(
                        f"Reaction counts - Yes: {yes_reactions}, No: {no_reactions}"
                    )

                    # Calculate vote percentage
                    total_votes = yes_reactions + no_reactions
                    vote_percentage = (
                        (yes_reactions / total_votes * 100) if total_votes > 0 else 0
                    )
                    logging.info(f"Vote percentage: {vote_percentage}%")

                    # Get current tags
                    current_tags = thread.applied_tags.copy()

                    # Remove our managed tags from current tags
                    current_tags = [
                        tag
                        for tag in current_tags
                        if tag.id
                        not in [not_added_tag.id, added_tag.id, initial_vote_tag.id]
                    ]

                    # Add appropriate tags based on conditions
                    if thread_age <= 24:
                        current_tags.append(initial_vote_tag)
                    else:
                        if vote_percentage >= 50:
                            current_tags.append(added_tag)
                        else:
                            current_tags.append(not_added_tag)

                    # Update thread tags
                    await thread.edit(applied_tags=current_tags)

                    # Ensure reaction emojis are present
                    yes_emoji = self.bot.get_emoji(1263941895625900085)
                    no_emoji = self.bot.get_emoji(1263941842244730972)

                    if first_message:
                        await first_message.add_reaction(yes_emoji)
                        await first_message.add_reaction(no_emoji)

                    fixed_count += 1
                    logging.info(f"Successfully processed thread {thread.id}")

                    # Update status every 10 threads
                    if fixed_count % 10 == 0:
                        await status_message.edit(
                            content=f"Fixed {fixed_count} threads... ({error_count} errors)"
                        )

                except Exception as e:
                    logging.error(f"Error fixing thread {thread.id}: {e}")
                    error_count += 1

            await status_message.edit(
                content=f"Process complete! Fixed {fixed_count} threads with {error_count} errors."
            )

        except Exception as e:
            logging.error(f"Error in fix_threads command: {e}", exc_info=True)
            await ctx.send(f"An error occurred: {str(e)}")

    @fix_threads.error
    async def fix_threads_error(self, ctx, error):
        """Error handler for fix_threads command"""
        logging.error(f"Error in fix_threads: {error}", exc_info=True)
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                "Please provide a channel ID. Usage: !fix_threads <channel_id>"
            )
        elif isinstance(error, commands.CommandInvokeError):
            await ctx.send(
                f"An error occurred while executing the command: {str(error)}"
            )
        else:
            await ctx.send(f"An unexpected error occurred: {str(error)}")

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """React to new threads in the tracked forum channel."""
        try:
            # Check if the thread is in the tracked forum channel
            server_config = self.config_manager.get_config(str(thread.guild.id))
            if (
                not server_config
                or str(thread.parent_id) != server_config.forum_channel_id
            ):
                return

            # Add Initial Vote tag immediately
            initial_vote_tag = discord.utils.get(
                thread.parent.available_tags, id=1315553680874803291
            )
            if initial_vote_tag:
                await thread.add_tags(initial_vote_tag)
                logging.info(f"Added Initial Vote tag to new thread: {thread.id}")

            # Add vote reactions
            await self.spreadsheet_service.manage_vote_reactions(thread, server_config)

        except Exception as e:
            logging.error(f"Error handling new thread {thread.id}: {e}")

    async def manage_thread_tags(self, thread, channel, vote_percentage, thread_age):
        """Helper function to manage thread tags consistently"""
        try:
            current_tags = thread.applied_tags.copy()
            tags_updated = False

            # Get all our managed tags
            initial_vote_tag = discord.utils.get(
                channel.available_tags, id=1315553680874803291
            )
            added_tag = discord.utils.get(
                channel.available_tags, id=1298038416025452585
            )
            not_added_tag = discord.utils.get(
                channel.available_tags, id=1258877875457626154
            )

            # Remove all managed tags first
            current_tags = [
                tag
                for tag in current_tags
                if tag.id
                not in [1315553680874803291, 1298038416025452585, 1258877875457626154]
            ]

            # Add appropriate tags based on conditions
            if thread_age < 24:
                current_tags.append(initial_vote_tag)
            else:
                if vote_percentage >= 50.1:
                    current_tags.append(added_tag)
                else:
                    current_tags.append(not_added_tag)

            # Update thread tags
            await thread.edit(applied_tags=current_tags)
            return True

        except Exception as e:
            logging.error(f"Error managing tags for thread {thread.id}: {e}")
            return False

    @tasks.loop(minutes=5)
    async def combined_sync_task(self):
        """Background task that handles tag management and spreadsheet sync"""
        try:
            logging.info("Starting combined sync task")
            guild = self.bot.get_guild(self.sync_guild_id)
            if not guild:
                logging.error(f"Could not find guild with ID {self.sync_guild_id}")
                return

            server_config = self.config_manager.get_config(str(guild.id))
            if not server_config or not server_config.forum_channel_id:
                return

            channel = guild.get_channel(int(server_config.forum_channel_id))
            if not isinstance(channel, discord.ForumChannel):
                return

            # Process all active threads
            threads = [thread for thread in channel.threads if not thread.archived]
            for thread in threads:
                try:
                    thread_age = (
                        discord.utils.utcnow() - thread.created_at
                    ).total_seconds() / 3600
                    first_message = await thread.fetch_message(thread.id)

                    if first_message:
                        # Count reactions
                        yes_count = no_count = 0
                        for reaction in first_message.reactions:
                            if isinstance(reaction.emoji, discord.Emoji):
                                if reaction.emoji.id == int(server_config.yes_emoji_id):
                                    yes_count = reaction.count - 1
                                elif reaction.emoji.id == int(
                                    server_config.no_emoji_id
                                ):
                                    no_count = reaction.count - 1

                        total_votes = yes_count + no_count
                        vote_percentage = (
                            (yes_count / total_votes * 100) if total_votes > 0 else 0
                        )

                        # Use the helper function to manage tags
                        updated = await self.manage_thread_tags(
                            thread, channel, vote_percentage, thread_age
                        )

                        # Handle 24-hour transition notifications
                        if 24 <= thread_age <= 24.1 and updated:
                            notification_channel = guild.get_channel(
                                1260691801577099295
                            )
                            if notification_channel:
                                result = "Won" if vote_percentage >= 50.1 else "Lost"
                                await notification_channel.send(
                                    f"[{thread.name}]({thread.jump_url}) -> {result} Quality Control"
                                )

                                # Sync to spreadsheet only for approved threads
                                if vote_percentage >= 50.1:
                                    await self.spreadsheet_service.sync_all_threads(
                                        guild, None
                                    )

                except Exception as e:
                    logging.error(f"Error processing thread {thread.id}: {e}")

        except Exception as e:
            logging.error(f"Error in combined sync task: {e}", exc_info=True)

    @combined_sync_task.before_loop
    async def before_combined_sync(self):
        """Wait for the bot to be ready before starting the task"""
        await self.bot.wait_until_ready()

    async def setup_hook(self) -> None:
        """This is called when the bot is starting up"""
        await self.bot.load_extension("src.settings")
        # Load other extensions...

        # Log what commands are available before sync
        logging.info(
            f"Commands before sync: {[cmd.name for cmd in self.bot.tree.get_commands()]}"
        )

        # Sync commands
        if self.sync_guild_id:
            guild = discord.Object(id=self.sync_guild_id)
            self.bot.tree.copy_global_to(guild=guild)
            await self.bot.tree.sync(guild=guild)
        else:
            await self.bot.tree.sync()

        # Log what commands are available after sync
        logging.info(
            f"Commands after sync: {[cmd.name for cmd in self.bot.tree.get_commands()]}"
        )

    async def check_and_initialize(self):
        """Check and initialize bot configuration"""
        server_config = self.config_manager.get_config(self.sync_guild_id)
        if server_config and server_config.is_configured:
            logging.info(
                "Bot is configured, initializing SpreadsheetService and starting background task"
            )
            await self.spreadsheet_service.initialize_google_api()
            self.sync_thread_tags.start()
            self.background_task_running = True
        else:
            logging.info(
                "Bot is not configured, skipping SpreadsheetService initialization and background task"
            )

    async def close(self):
        """Cleanup method called when the bot is shutting down"""
        logging.info("Closing bot and database session")
        if self.background_task_running:
            self.sync_thread_tags.cancel()
        await super().close()

    def cog_load(self) -> None:
        """Called when the cog is loaded"""
        logging.info(
            f"DiscordBot cog loaded with commands: {[cmd.name for cmd in self.get_commands()]}"
        )


async def setup(bot: commands.Bot):
    """
    Sets up the DiscordBot cog and adds it to the bot.

    This function is called by the bot when loading extensions.
    """
    config_manager = bot.config_manager
    session = bot.session
    cog = DiscordBot(bot, config_manager, session)
    await bot.add_cog(cog)
    logging.info(
        f"DiscordBot cog loaded with commands: {', '.join([command.name for command in cog.get_commands()])}"
    )
