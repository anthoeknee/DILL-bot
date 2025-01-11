# src/spreadsheets.py
from google.oauth2 import service_account
from googleapiclient.discovery import build
from src.config import load_config, ConfigManager
from src.utils import load_google_credentials
import logging
import discord
from typing import List, Dict, Optional, Set
from sqlalchemy.orm import Session
from src.models import ServerConfig, Thread, Tag
import json
from discord.ext import commands
from datetime import datetime
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

config = load_config()


class SpreadsheetService:
    def __init__(self, session: Session, bot: commands.Bot):
        self.session = session
        self.bot = bot
        self.config_manager = ConfigManager(session)
        self.service = None
        logging.info("SpreadsheetService initialized.")
        self.notification_channel_id = 1260691801577099295
        self.last_thread_states = {}  # Store previous vote states

    async def initialize_google_api(self, server_id: Optional[str] = None):
        logging.info("Initializing Google Sheets API.")
        if not server_id:
            server_config = self.config_manager.get_config()
        else:
            server_config = self.config_manager.get_config(server_id)
        if not server_config:
            logging.error(
                "No server config found, cannot initialize Google Sheets API."
            )
            return False
        credentials = self.config_manager.get_google_credentials()
        if not credentials:
            logging.error(
                "No google credentials found, cannot initialize Google Sheets API."
            )
            return False
        try:
            creds = load_google_credentials(json.dumps(credentials))
            self.service = build("sheets", "v4", credentials=creds)
            logging.info("Google Sheets API initialized successfully.")
            return True
        except Exception as e:
            logging.error(f"Error initializing Google Sheets API: {e}")
            return False

    async def initialize(self) -> bool:
        logging.info("Initializing SpreadsheetService.")
        return await self.initialize_google_api()

    async def sync_all_threads(
        self, guild: discord.Guild, progress_message: discord.Message
    ):
        """Synchronize all threads in the guild's forum channel with the spreadsheet"""
        logging.info(f"Syncing all threads for guild: {guild.id}")

        # Initialize Google Sheets API first
        if not await self.initialize_google_api(str(guild.id)):
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
        is_first_sync = not self.last_thread_states

        # Get ALL threads (both active and archived) and sort them by creation date
        all_threads = []
        async for thread in channel.archived_threads():
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

            for thread in batch:
                current_tags = set(tag.name for tag in thread.applied_tags)
                task = self.process_thread_data(
                    thread=thread,
                    config=server_config,
                    available_tags=available_tags,
                    current_tags=current_tags,
                    skip_notifications=is_first_sync,
                )
                batch_tasks.append(task)

            # Process batch concurrently
            batch_results = await asyncio.gather(*batch_tasks)
            all_thread_data.extend([data for data in batch_results if data])

            # Update progress
            progress = min((i + batch_size) / total_threads * 100, 100)
            processed = min(i + batch_size, total_threads)
            progress_status = (
                f"Processing threads: {processed}/{total_threads} ({progress:.1f}%)"
            )
            await progress_message.edit(content=progress_status)
            logging.info(progress_status)

        if all_thread_data:
            await self.update_sheet(all_thread_data, server_config)
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
        logging.info(f"Processing thread data for thread: {thread.id}")
        try:
            # Skip threads with "Initial Voting" tag
            if "Initial Voting" in current_tags:
                return None

            first_message = await self.fetch_first_message(thread)
            if not first_message:
                logging.warning(f"No first message found for thread: {thread.id}")
                return None

            # Count reactions
            yes_count = 0
            no_count = 0
            for reaction in first_message.reactions:
                if isinstance(reaction.emoji, discord.Emoji):
                    if reaction.emoji.id == int(config.yes_emoji_id):
                        yes_count = reaction.count - 1
                    elif reaction.emoji.id == int(config.no_emoji_id):
                        no_count = reaction.count - 1

            total_votes = yes_count + no_count
            ratio = (yes_count / total_votes * 100) if total_votes > 0 else 0

            thread_id = str(thread.id)
            prev_ratio = self.last_thread_states.get(thread_id, 0)

            # Only send notification if not skipping notifications and threshold is crossed
            if not skip_notifications and prev_ratio <= 50 and ratio > 50:
                await self.send_approval_notification(thread)

            # Always update the last known state
            self.last_thread_states[thread_id] = ratio

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

    async def process_thread(self, thread: discord.Thread, config: ServerConfig):
        logging.info(f"Processing thread: {thread.id}")
        try:
            await self.manage_vote_reactions(thread, config)
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

            tags_to_add = []
            tags_to_remove = []

            # Get the current tags on the thread
            current_tags = set([tag.name for tag in thread.applied_tags])

            # Get the tag mappings from the config
            tag_mappings = config.tag_mappings or {}

            # Check for tags to add
            for tag_name, tag_id in tag_mappings.items():
                if tag_id and tag_name not in current_tags:
                    tags_to_add.append(tag_name)

            # Check for tags to remove
            for tag_name in current_tags:
                if tag_name not in tag_mappings:
                    tags_to_remove.append(tag_name)

            await self.update_thread_tags(thread, tags_to_add, tags_to_remove)
            logging.info(f"Finished processing thread: {thread.id}")
        except Exception as e:
            logging.error(f"Error processing thread {thread.id}: {e}")

    async def update_thread_tags(
        self, thread: discord.Thread, tags_to_add: List[str], tags_to_remove: List[str]
    ):
        logging.info(
            f"Updating tags for thread: {thread.id}. Adding: {tags_to_add}, Removing: {tags_to_remove}"
        )
        try:
            for tag_name in tags_to_add:
                tag = self.session.query(Tag).filter_by(name=tag_name).first()
                if tag:
                    await thread.add_tags(tag.id)
                    logging.info(f"Added tag '{tag_name}' to thread: {thread.id}")
                else:
                    logging.warning(
                        f"Tag '{tag_name}' not found in database, skipping."
                    )
            for tag_name in tags_to_remove:
                tag = self.session.query(Tag).filter_by(name=tag_name).first()
                if tag:
                    await thread.remove_tags(tag.id)
                    logging.info(f"Removed tag '{tag_name}' from thread: {thread.id}")
                else:
                    logging.warning(
                        f"Tag '{tag_name}' not found in database, skipping."
                    )
        except Exception as e:
            logging.error(f"Error updating tags for thread {thread.id}: {e}")

    async def fetch_first_message(
        self, thread: discord.Thread
    ) -> Optional[discord.Message]:
        logging.info(f"Fetching first message for thread: {thread.id}")
        try:
            messages = [
                message async for message in thread.history(limit=1, oldest_first=True)
            ]
            if messages:
                logging.info(f"First message found for thread: {thread.id}")
                return messages[0]
            else:
                logging.warning(f"No messages found for thread: {thread.id}")
                return None
        except Exception as e:
            logging.error(f"Error fetching first message for thread {thread.id}: {e}")
            return None

    async def update_sheet(self, thread_data: List[Dict], config: ServerConfig):
        logging.info(f"Updating Google Sheet with {len(thread_data)} threads.")
        try:
            if not self.service:
                logging.error("Google Sheets service not initialized")
                return

            if not thread_data:
                logging.warning("No thread data to update")
                return

            # First, clear all existing data below headers
            clear_range = "B2:G1000"  # Adjust range as needed
            try:
                self.service.spreadsheets().values().clear(
                    spreadsheetId=config.spreadsheet_id, range=clear_range
                ).execute()
                logging.info("Cleared existing spreadsheet data")
            except Exception as e:
                logging.error(f"Error clearing spreadsheet: {e}")
                return

            # Prepare the values starting from B2
            values = []
            for data in thread_data:
                row = [
                    data["thread_name"],
                    data["yes_count"],
                    data["no_count"],
                    data["tags"],
                    data["ratio"],
                    data["date_posted"],
                ]
                values.append(row)

            # Update the sheet starting from B2
            range_name = f"B2:G{len(values) + 1}"
            body = {"values": values}

            logging.info(
                f"Attempting to update {len(values)} rows in range {range_name}"
            )

            request = (
                self.service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=config.spreadsheet_id,
                    range=range_name,
                    valueInputOption="USER_ENTERED",
                    body=body,
                )
            )
            response = request.execute()

            updated_cells = response.get("updatedCells", 0)
            updated_rows = response.get("updatedRows", 0)
            logging.info(
                f"Successfully updated {updated_cells} cells across {updated_rows} rows"
            )

        except Exception as e:
            logging.error(f"Error updating Google Sheet: {e}", exc_info=True)
            raise  # Re-raise the exception so the command can catch it

    async def autocomplete_channels(
        self, interaction: discord.Interaction, current: str
    ) -> List[discord.app_commands.Choice]:
        logging.info(f"Autocompleting channels with current: {current}")
        choices = []
        for guild in self.bot.guilds:
            for channel in guild.channels:
                if (
                    isinstance(channel, discord.TextChannel)
                    and current.lower() in channel.name.lower()
                ):
                    choices.append(
                        discord.app_commands.Choice(
                            name=f"{guild.name} - {channel.name}", value=str(channel.id)
                        )
                    )
        return choices[:25]

    async def manage_vote_reactions(self, thread: discord.Thread, config: ServerConfig):
        logging.info(f"Managing vote reactions for thread: {thread.id}")
        try:
            first_message = await self.fetch_first_message(thread)
            if not first_message:
                logging.warning(
                    f"No first message found for thread: {thread.id}, skipping vote reaction management."
                )
                return

            yes_emoji_id = config.yes_emoji_id
            no_emoji_id = config.no_emoji_id
            if not yes_emoji_id or not no_emoji_id:
                logging.warning(
                    f"Yes or No emoji IDs not set for server {thread.guild.id}, skipping vote reaction management."
                )
                return

            yes_emoji = self.bot.get_emoji(int(yes_emoji_id))
            no_emoji = self.bot.get_emoji(int(no_emoji_id))

            if not yes_emoji or not no_emoji:
                logging.warning(
                    f"Could not find emojis for server {thread.guild.id}. Yes emoji: {yes_emoji}, No emoji: {no_emoji}"
                )
                return

            # Always add both reactions
            await first_message.add_reaction(yes_emoji)
            await first_message.add_reaction(no_emoji)
            logging.info(f"Added/Updated reactions for thread: {thread.id}")

        except Exception as e:
            logging.error(
                f"Error managing vote reactions for thread {thread.id}: {e}",
                exc_info=True,
            )

    async def send_approval_notification(self, thread: discord.Thread):
        """Send notification when a thread crosses 50% approval"""
        try:
            channel = self.bot.get_channel(self.notification_channel_id)
            if channel:
                await channel.send(
                    f"🎉 Level **{thread.name}** has reached over 50% approval! {thread.jump_url}"
                )
        except Exception as e:
            logging.error(f"Error sending approval notification: {e}")


def get_sheets_service():
    creds = service_account.Credentials.from_service_account_file(
        config["google"]["credentials_path"],
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds)
    return service


def read_spreadsheet(range_name):
    service = get_sheets_service()
    sheet = service.spreadsheets()
    result = (
        sheet.values()
        .get(spreadsheetId=config["google"]["spreadsheet_id"], range=range_name)
        .execute()
    )
    values = result.get("values", [])
    return values
