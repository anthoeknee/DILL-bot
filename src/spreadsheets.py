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
