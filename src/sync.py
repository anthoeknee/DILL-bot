import discord
from discord.ext import commands, tasks
from src.spreadsheets import SpreadsheetService
from src.config import ConfigManager
from src.models import ServerConfig, Thread, Tag
import logging
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Set
import os
import asyncio


class SyncCog(commands.Cog, name="Synchronization"):
    """Handles synchronization of threads with the spreadsheet and tag management."""

    def __init__(
        self,
        bot: commands.Bot,
        config_manager: ConfigManager,
        session: Session,
    ):
        self.bot = bot
        self.config_manager = config_manager
        self.session = session
        self.spreadsheet_service = SpreadsheetService(self.session, bot)
        self.sync_guild_id = int(os.getenv("SYNC_GUILD_ID", "0"))
        self.background_task_running = False
        logging.info("SyncCog initialized.")
        self.tag_ids = {
            "initial_vote": 1315553680874803291,
            "added_to_list": 1298038416025452585,
            "not_added_to_list": 1258877875457626154,
        }
        self.manage_tags_task.start()

    async def sync_all_threads(
        self,
        guild: discord.Guild,
        progress_message: Optional[discord.Message] = None,
    ):
        """Synchronize all threads in the forum channel with the Google Spreadsheet."""
        logging.info(f"Syncing all threads for guild: {guild.id}")

        # Initialize Google Sheets API first
        if not await self.spreadsheet_service.initialize_google_api(str(guild.id)):
            raise ValueError("Failed to initialize Google Sheets API")

        server_config = (
            self.session.query(ServerConfig).filter_by(server_id=str(guild.id)).first()
        )

        if not server_config or not server_config.forum_channel_id:
            raise ValueError("Forum channel not configured")

        channel = guild.get_channel(int(server_config.forum_channel_id))
        if not isinstance(channel, discord.ForumChannel):
            raise ValueError("Configured channel is not a forum channel")

        # Get all available tags in the forum
        available_tags = {tag.name: tag for tag in channel.available_tags}

        # Store whether this is the first sync
        is_first_sync = not self.spreadsheet_service.last_thread_states

        # Get ALL threads (both active and archived) and sort them by creation date
        all_threads = []
        async for thread in channel.archived_threads(limit=None):
            all_threads.append(thread)
        all_threads.extend(channel.threads)

        all_threads.sort(key=lambda x: x.created_at, reverse=True)

        total_threads = len(all_threads)

        if total_threads == 0:
            return "No threads found to sync."

        all_thread_data = []
        batch_size = 10  # Process 10 threads at a time

        for i in range(0, total_threads, batch_size):
            batch = all_threads[i : i + batch_size]
            batch_tasks = []
            reaction_tasks = []  # New list for reaction management tasks

            for thread in batch:
                # Unarchive the thread if it's archived
                if thread.archived:
                    await thread.edit(archived=False)
                    logging.info(f"Unarchived thread: {thread.id}")

                # Wait for a short period to ensure tags are updated
                await asyncio.sleep(1)

                # Fetch the current tags again after the delay
                current_tags = set(tag.name for tag in thread.applied_tags)
                logging.info(f"Current tags for thread {thread.id}: {current_tags}")

                # Add thread data processing task
                task = self.process_thread_data(
                    thread=thread,
                    config=server_config,
                    available_tags=available_tags,
                    current_tags=current_tags,
                    skip_notifications=is_first_sync,
                )
                batch_tasks.append(task)

                # Add reaction management task
                reaction_task = self.spreadsheet_service.manage_vote_reactions(
                    thread, server_config
                )
                reaction_tasks.append(reaction_task)

            # Process batch concurrently
            batch_results = await asyncio.gather(*batch_tasks)
            await asyncio.gather(*reaction_tasks)  # Process reaction tasks
            all_thread_data.extend([data for data in batch_results if data])

            # Update progress
            progress = min((i + batch_size) / total_threads * 100, 100)
            processed = min(i + batch_size, total_threads)
            progress_status = (
                f"Processing threads: {processed}/{total_threads} ({progress:.1f}%)"
            )
            if progress_message:
                await progress_message.edit(content=progress_status)
            logging.info(progress_status)

        if all_thread_data:
            await self.spreadsheet_service.update_sheet(all_thread_data, server_config)
            return f"✅ Sync complete! Processed {len(all_thread_data)} threads."
        else:
            return "No thread data was collected to sync."

    async def process_thread_data(
        self,
        thread: discord.Thread,
        config: ServerConfig,
        available_tags: Dict[str, discord.ForumTag],
        current_tags: Set[str],
        skip_notifications: bool = False,
    ) -> Optional[Dict]:
        """Processes data for a single thread, including vote counting and tag management."""
        logging.debug(f"Processing thread data for thread: {thread.id}")
        try:
            # Skip threads with "Initial Voting" tag
            if "Initial Voting" in current_tags:
                return None

            first_message = await self.spreadsheet_service.fetch_first_message(thread)
            if not first_message:
                logging.debug(f"No first message found for thread: {thread.id}")
                return None

            # Define accepted emojis
            yes_emojis = {
                "custom": int(config.yes_emoji_id),  # Your custom pickle_yes
                "check": "✅",  # Unicode white_check_mark
                "check2": "☑️",  # Unicode ballot_box_with_check
            }
            no_emojis = {
                "custom": int(config.no_emoji_id),  # Your custom pickle_no
                "x": "❌",  # Unicode x
                "x2": "✖️",  # Unicode heavy_multiplication_x
            }

            # Count reactions
            yes_count = 0
            no_count = 0

            for reaction in first_message.reactions:
                # Handle custom emoji
                if isinstance(reaction.emoji, discord.Emoji):
                    emoji_id = reaction.emoji.id
                    if emoji_id == yes_emojis["custom"]:
                        yes_count += reaction.count - 1
                    elif emoji_id == no_emojis["custom"]:
                        no_count += reaction.count - 1
                # Handle Unicode emoji
                else:
                    emoji_str = str(reaction.emoji)
                    if emoji_str in yes_emojis.values():
                        yes_count += reaction.count - 1
                    elif emoji_str in no_emojis.values():
                        no_count += reaction.count - 1

            total_votes = yes_count + no_count
            ratio = (yes_count / total_votes * 100) if total_votes > 0 else 0

            thread_id = str(thread.id)
            prev_ratio = self.spreadsheet_service.last_thread_states.get(thread_id, 0)

            # Only send notification if not skipping notifications and threshold is crossed
            if not skip_notifications and prev_ratio <= 50 and ratio > 50:
                await self.spreadsheet_service.send_approval_notification(thread)

            # Always update the last known state
            self.spreadsheet_service.last_thread_states[thread_id] = ratio

            return {
                "thread_name": thread.name,
                "yes_count": yes_count,
                "no_count": no_count,
                "tags": ", ".join(current_tags),
                "ratio": f"{ratio:.2f}%",
                "date_posted": thread.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            logging.error(f"Error processing thread data for thread {thread.id}: {e}")
            return None

    async def manage_thread_tags(
        self,
        thread: discord.Thread,
        channel: discord.ForumChannel,
        vote_percentage: float,
        thread_age: float,
    ):
        """Helper function to manage thread tags consistently."""
        logging.info(f"Managing tags for thread: {thread.id}")
        try:
            # Fetch the thread from the database
            db_thread = (
                self.session.query(Thread).filter_by(thread_id=str(thread.id)).first()
            )
            if not db_thread:
                logging.info(
                    f"Thread {thread.id} not found in database, creating new entry."
                )
                db_thread = Thread(thread_id=str(thread.id))
                self.session.add(db_thread)
                self.session.commit()

            # Get the current tags on the thread
            current_tags = set([tag.name for tag in thread.applied_tags])

            # Get the tag mappings from the config
            server_config = self.config_manager.get_config(str(thread.guild.id))
            tag_mappings = server_config.tag_mappings or {}

            # Determine tags to add and remove based on thread age and vote percentage
            tags_to_add = []
            tags_to_remove = []

            initial_vote_tag_name = discord.utils.get(
                channel.available_tags, id=self.tag_ids["initial_vote"]
            ).name
            added_to_list_tag_name = discord.utils.get(
                channel.available_tags, id=self.tag_ids["added_to_list"]
            ).name
            not_added_to_list_tag_name = discord.utils.get(
                channel.available_tags, id=self.tag_ids["not_added_to_list"]
            ).name

            if thread_age <= 24:
                # Add "Initial Vote" tag if not present
                if initial_vote_tag_name not in current_tags:
                    tags_to_add.append(initial_vote_tag_name)
                # Remove "Added to List" and "Not Added to List" tags if present
                if added_to_list_tag_name in current_tags:
                    tags_to_remove.append(added_to_list_tag_name)
                if not_added_to_list_tag_name in current_tags:
                    tags_to_remove.append(not_added_to_list_tag_name)
            else:
                # Remove "Initial Vote" tag if present
                if initial_vote_tag_name in current_tags:
                    tags_to_remove.append(initial_vote_tag_name)
                # Add "Added to List" or "Not Added to List" tag based on vote percentage
                if vote_percentage >= 50.1:
                    if added_to_list_tag_name not in current_tags:
                        tags_to_add.append(added_to_list_tag_name)
                    if not_added_to_list_tag_name in current_tags:
                        tags_to_remove.append(not_added_to_list_tag_name)
                else:
                    if not_added_to_list_tag_name not in current_tags:
                        tags_to_add.append(not_added_to_list_tag_name)
                    if added_to_list_tag_name in current_tags:
                        tags_to_remove.append(added_to_list_tag_name)

            # Update thread tags
            await self.update_thread_tags(thread, tags_to_add, tags_to_remove)
            logging.info(f"Finished managing tags for thread: {thread.id}")
            return True  # Indicate that tags were updated
        except Exception as e:
            logging.error(f"Error managing tags for thread {thread.id}: {e}")
            return False

    async def update_thread_tags(
        self, thread: discord.Thread, tags_to_add: List[str], tags_to_remove: List[str]
    ):
        """Updates the tags of a given thread based on the provided lists of tags to add and remove."""
        logging.debug(
            f"Updating tags for thread: {thread.id}. Adding: {tags_to_add}, Removing: {tags_to_remove}"
        )
        try:
            # Get the available tags from the forum channel
            available_tags = {tag.name: tag for tag in thread.parent.available_tags}
            current_tags = set([tag.name for tag in thread.applied_tags])

            # Determine tags to be added and removed
            tags_to_add_set = set(tags_to_add) - current_tags
            tags_to_remove_set = set(tags_to_remove) & current_tags

            # Prepare the new set of tags
            new_tags = (current_tags - tags_to_remove_set) | tags_to_add_set
            new_tag_objects = [
                available_tags[tag_name]
                for tag_name in new_tags
                if tag_name in available_tags
            ]

            # Update the thread tags if there are changes
            if set(new_tag_objects) != set(thread.applied_tags):
                await thread.edit(applied_tags=new_tag_objects)
                logging.debug(f"Updated tags for thread: {thread.id}")
            else:
                logging.debug(f"No tag changes needed for thread: {thread.id}")

        except Exception as e:
            logging.error(f"Error updating tags for thread {thread.id}: {e}")

    @tasks.loop(minutes=5)
    async def manage_tags_task(self):
        """Background task to manage thread tags based on age and vote percentage."""
        logging.info("Starting manage_tags_task")
        try:
            guild = self.bot.get_guild(self.sync_guild_id)
            if not guild:
                logging.error(f"Could not find guild with ID {self.sync_guild_id}")
                return

            server_config = self.config_manager.get_config(str(guild.id))
            if not server_config or not server_config.forum_channel_id:
                logging.info(
                    "Server not configured or forum channel ID not set, skipping manage_tags_task"
                )
                return

            channel = guild.get_channel(int(server_config.forum_channel_id))
            if not isinstance(channel, discord.ForumChannel):
                logging.info(
                    "Configured channel is not a ForumChannel, skipping manage_tags_task"
                )
                return

            # Get ALL threads (both active and archived)
            all_threads = []
            async for thread in channel.archived_threads(limit=None):
                all_threads.append(thread)
            all_threads.extend(channel.threads)

            for thread in all_threads:
                try:
                    thread_age = (
                        discord.utils.utcnow() - thread.created_at
                    ).total_seconds() / 3600

                    # Fetch the first message to count reactions
                    first_message = await self.spreadsheet_service.fetch_first_message(
                        thread
                    )
                    yes_count = no_count = 0
                    if first_message:
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

                    # Manage tags
                    await self.manage_thread_tags(
                        thread, channel, vote_percentage, thread_age
                    )

                except Exception as e:
                    logging.error(f"Error processing thread {thread.id}: {e}")

        except Exception as e:
            logging.error(f"Error in manage_tags_task: {e}", exc_info=True)

    @manage_tags_task.before_loop
    async def before_manage_tags_task(self):
        """Wait for the bot to be ready before starting the task."""
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=30)
    async def combined_sync_task(self):
        """Background task for spreadsheet synchronization only."""
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

            # Get ALL threads (both active and archived)
            all_threads = []
            async for thread in channel.archived_threads(limit=None):
                all_threads.append(thread)
            all_threads.extend(channel.threads)
            total_threads = len(all_threads)
            logging.info(f"Processing {total_threads} threads")

            # ... rest of your spreadsheet sync logic ...

        except Exception as e:
            logging.error(f"Error in combined sync task: {e}", exc_info=True)

    @combined_sync_task.before_loop
    async def before_combined_sync(self):
        """Wait for the bot to be ready before starting the task."""
        await self.bot.wait_until_ready()

    async def check_and_initialize(self):
        """Check and initialize bot configuration"""
        server_config = self.config_manager.get_config(self.sync_guild_id)
        if server_config and server_config.is_configured:
            logging.info(
                "Bot is configured, initializing SpreadsheetService and starting background tasks"
            )
            await self.spreadsheet_service.initialize_google_api()
            self.combined_sync_task.start()
            self.manage_tags_task.start()
            self.background_task_running = True
        else:
            logging.info(
                "Bot is not configured, skipping SpreadsheetService initialization and background task"
            )

    async def close(self):
        """Cleanup method called when the bot is shutting down."""
        logging.info("Closing SyncCog and related tasks.")
        if self.background_task_running:
            self.combined_sync_task.cancel()
            self.manage_tags_task.cancel()


async def setup(bot: commands.Bot):
    """
    Sets up the SyncCog and adds it to the bot.

    This function is called by the bot when loading extensions.
    """
    config_manager = bot.config_manager
    session = bot.session
    cog = SyncCog(bot, config_manager, session)
    await bot.add_cog(cog)
    logging.info(f"SyncCog loaded.")
