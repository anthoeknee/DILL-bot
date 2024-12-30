# src/spreadsheets.py
from google.oauth2 import service_account
from googleapiclient.discovery import build
from src.config import load_config, ConfigManager
from src.utils import load_google_credentials
import logging
import discord
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from src.models import ServerConfig, Thread, Tag
import json
from discord.ext import commands

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
        credentials = server_config.get_google_credentials()
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

    async def sync_all_threads(self, guild: discord.Guild):
        logging.info(f"Syncing all threads for guild: {guild.id}")
        server_config = self.config_manager.get_config(str(guild.id))
        if not server_config or not server_config.is_configured:
            logging.warning(f"Server {guild.id} is not configured, skipping sync.")
            return
        if not server_config.forum_channel_id:
            logging.warning(
                f"Forum channel ID is not set for server {guild.id}, skipping sync."
            )
            return
        forum_channel = self.bot.get_channel(int(server_config.forum_channel_id))
        if not forum_channel:
            logging.error(
                f"Forum channel with ID {server_config.forum_channel_id} not found for server {guild.id}."
            )
            return
        threads = [thread for thread in forum_channel.threads if not thread.archived]
        all_thread_data = []
        for thread in threads:
            if (
                server_config.exempt_threads
                and str(thread.id) in server_config.exempt_threads
            ):
                logging.info(f"Skipping exempt thread: {thread.id}")
                continue
            thread_data = await self.process_thread_data(thread, server_config)
            if thread_data:
                all_thread_data.append(thread_data)
        if all_thread_data:
            await self.update_sheet(all_thread_data, server_config)
        logging.info(f"Finished syncing all threads for guild: {guild.id}")

    async def process_thread_data(
        self, thread: discord.Thread, config: ServerConfig
    ) -> Optional[Dict]:
        logging.info(f"Processing thread data for thread: {thread.id}")
        try:
            first_message = await self.fetch_first_message(thread)
            if not first_message:
                logging.warning(f"No first message found for thread: {thread.id}")
                return None
            thread_data = {
                "thread_id": str(thread.id),
                "thread_name": thread.name,
                "first_message_content": first_message.content,
                "first_message_author": str(first_message.author.id),
                "tags": [tag.name for tag in thread.applied_tags],
                "url": thread.jump_url,
            }
            return thread_data
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
        logging.info("Updating Google Sheet with thread data.")
        try:
            if not self.service:
                logging.error("Google Sheets API not initialized, cannot update sheet.")
                return
            spreadsheet_id = config.spreadsheet_id
            if not spreadsheet_id:
                logging.error("Spreadsheet ID not set, cannot update sheet.")
                return
            sheet = self.service.spreadsheets()
            values = [list(data.values()) for data in thread_data]
            header = list(thread_data[0].keys()) if thread_data else []
            body = [header] + values
            range_name = "A1"
            value_input_option = "USER_ENTERED"
            value_range_body = {"values": body}
            request = sheet.values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                body=value_range_body,
            )
            response = request.execute()
            logging.info(
                f"Google Sheet updated successfully. Updated {response.get('updatedCells', 0)} cells."
            )
        except Exception as e:
            logging.error(f"Error updating Google Sheet: {e}")

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
                    f"Yes or No emojis not found for server {thread.guild.id}, skipping vote reaction management."
                )
                return

            if not any(
                reaction.emoji == yes_emoji for reaction in first_message.reactions
            ):
                await first_message.add_reaction(yes_emoji)
                logging.info(f"Added yes reaction to thread: {thread.id}")
            if not any(
                reaction.emoji == no_emoji for reaction in first_message.reactions
            ):
                await first_message.add_reaction(no_emoji)
                logging.info(f"Added no reaction to thread: {thread.id}")
        except Exception as e:
            logging.error(f"Error managing vote reactions for thread {thread.id}: {e}")


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
