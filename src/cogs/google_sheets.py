import discord
from discord import app_commands
from discord.ext import commands, tasks
from typing import Dict, Any, Optional
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json
from pathlib import Path
from src.utils.checks import is_owner, is_admin_or_owner
from src.utils.settings_manager import SettingType
from src.utils.logger import logger
from datetime import datetime
import asyncio
from src.config import config
class GoogleSheets(commands.GroupCog):
    """Manage Google Sheets integration for forum tracking"""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sheet_service = None
        self.last_updates = {}
        self._setup_google_sheets()
        self.update_tracker.start()

    def cog_unload(self):
        self.update_tracker.cancel()

    def _setup_google_sheets(self):
        """Initialize Google Sheets API service"""
        try:
            credentials_path = Path(__file__).parent.parent.parent / "data" / "google-credentials.json"
            if not credentials_path.exists():
                logger.error(f"Google credentials file not found at {credentials_path}")
                return
            
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path),
                scopes=['https://www.googleapis.com/auth/spreadsheets']
            )
            self.sheet_service = build('sheets', 'v4', credentials=credentials)
        except Exception as e:
            logger.error(f"Failed to setup Google Sheets: {e}")

    async def _process_thread(self, thread: discord.Thread) -> Optional[Dict[str, Any]]:
        """Process a single thread and return its data"""
        try:
            # Get the first message
            first_message = await thread.fetch_message(thread.id)
            
            # Get reaction counts
            yes_votes = sum([
                reaction.count 
                for reaction in first_message.reactions 
                if str(reaction.emoji) in [
                    "<:pickle_yes:1263941895625900085>",
                    "<:abobaheavenlymerveilleuxinstantw:1166782218849484810>"
                ]
            ])
            
            no_votes = sum([
                reaction.count 
                for reaction in first_message.reactions 
                if str(reaction.emoji) == "<:pickle_no:1263941842244730972>"
            ])
            
            # Calculate ratio
            total_votes = yes_votes + no_votes
            ratio = f"{(yes_votes / total_votes * 100):.1f}%" if total_votes > 0 else "0%"
            
            return {
                'thread_id': str(thread.id),
                'title': thread.name,
                'content': first_message.content[:500] if first_message.content else "No content",
                'yes_votes': yes_votes,
                'no_votes': no_votes,
                'ratio': ratio,
                'date_posted': thread.created_at.strftime("%Y-%m-%d %H:%M:%S")
            }
            
        except Exception as e:
            logger.error(f"Error processing thread {thread.id}: {e}")
            return None

    def _update_spreadsheet(self, spreadsheet_id: str, updates: Dict[str, Any]):
        """Handle all spreadsheet updates"""
        if updates['to_delete']:
            requests = [{
                'deleteDimension': {
                    'range': {
                        'sheetId': 0,
                        'dimension': 'ROWS',
                        'startIndex': row - 1,
                        'endIndex': row
                    }
                }
            } for row in sorted(updates['to_delete'], reverse=True)]
            
            self.sheet_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={'requests': requests}
            ).execute()

        if updates['to_update']:
            self.sheet_service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={
                    'valueInputOption': 'RAW',
                    'data': updates['to_update']
                }
            ).execute()

        if updates['to_add']:
            self.sheet_service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range="B2:G2",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": updates['to_add']}
            ).execute()

    @tasks.loop(minutes=1)
    async def update_tracker(self):
        """Update forum posts data based on settings"""
        for guild in self.bot.guilds:
            try:
                forum_data = self.bot.settings.get(guild.id, "forum_tracker")
                if not forum_data:
                    continue
                    
                forum_data = json.loads(forum_data)
                interval = forum_data.get("update_interval", 5)
                
                if interval != "on_change":
                    current_time = datetime.now()
                    last_update = self.last_updates.get(guild.id, datetime.min)
                    if (current_time - last_update).total_seconds() < (interval * 60):
                        continue
                
                await self.update_forum_data(guild.id, forum_data)
                self.last_updates[guild.id] = datetime.now()
            except Exception as e:
                logger.error(f"Error updating forum data for guild {guild.id}: {e}")

    @update_tracker.before_loop
    async def before_update_tracker(self):
        await self.bot.wait_until_ready()

    async def update_forum_data(self, guild_id: int, forum_data: Dict[str, Any]):
        """Update spreadsheet with forum data"""
        forum_channel = self.bot.get_channel(forum_data["forum_id"])
        if not forum_channel:
            return

        try:
            # Get existing data and current threads concurrently
            existing_data_task = asyncio.create_task(
                asyncio.to_thread(
                    self.sheet_service.spreadsheets().values().get(
                        spreadsheetId=forum_data["spreadsheet_id"],
                        range="B2:G"  # Changed to B2:G for 6 columns
                    ).execute
                )
            )

            # Create a single list of all threads first
            all_threads = []
            
            # Add active threads
            all_threads.extend(forum_channel.threads)
            
            # Add archived threads if enabled
            if forum_data.get("load_history", False):
                try:
                    archived_threads = [
                        thread async for thread in forum_channel.archived_threads(limit=None)
                    ]
                    all_threads.extend(archived_threads)
                except Exception as e:
                    logger.error(f"Error fetching archived threads: {e}")

            # Create the thread mapping AFTER collecting all threads
            current_threads = {thread.name: thread for thread in all_threads}
            
            # Sort threads by thread ID (more reliable than creation time)
            sorted_threads = sorted(
                all_threads,
                key=lambda x: x.id
            )

            # Wait for existing data
            existing_data = await existing_data_task
            existing_values = existing_data.get('values', [])
            existing_threads = {
                row[0]: i + 2 
                for i, row in enumerate(existing_values)
                if row and row[0]
            }

            # Process threads in batches while maintaining order
            BATCH_SIZE = 10
            thread_data_with_timestamps = []  # Store data with timestamps for sorting

            # Process threads in batches to gather data
            for i in range(0, len(sorted_threads), BATCH_SIZE):
                batch = sorted_threads[i:i + BATCH_SIZE]
                thread_tasks = [self._process_thread(thread) for thread in batch]
                thread_data_list = await asyncio.gather(*thread_tasks)
                
                for thread, thread_data in zip(batch, thread_data_list):
                    if thread_data:
                        # Store creation timestamp with the data
                        thread_data_with_timestamps.append((
                            thread.created_at,
                            thread,
                            thread_data
                        ))

            # Sort again by timestamp to ensure chronological order
            thread_data_with_timestamps.sort(key=lambda x: x[0])

            updates = {
                'to_delete': [],
                'to_update': [],
                'to_add': []
            }

            # Handle deletions first
            updates['to_delete'] = [
                row_num for thread_name, row_num in existing_threads.items()
                if thread_name not in current_threads
            ]

            # Process threads in chronological order
            for _, thread, thread_data in thread_data_with_timestamps:
                row_data = [
                    thread_data["title"],
                    thread_data["content"],
                    thread_data["yes_votes"],
                    thread_data["no_votes"],
                    thread_data["ratio"],
                    thread_data["date_posted"]
                ]

                if thread.name in existing_threads:
                    updates['to_update'].append({
                        'range': f'B{existing_threads[thread.name]}:G{existing_threads[thread.name]}',
                        'values': [row_data]
                    })
                else:
                    updates['to_add'].append(row_data)

            # Batch update spreadsheet
            if any(updates.values()):
                await asyncio.to_thread(
                    lambda: self._update_spreadsheet(forum_data["spreadsheet_id"], updates)
                )

            # Log statistics
            logger.info(f"Spreadsheet update complete for guild {guild_id}:")
            logger.info(f"- Updated {len(updates['to_update'])} existing entries")
            logger.info(f"- Added {len(updates['to_add'])} new entries")
            logger.info(f"- Deleted {len(updates['to_delete'])} removed entries")

        except Exception as e:
            logger.error(f"Error updating spreadsheet: {e}")

    @app_commands.command(name="setup_forum_tracker")
    @app_commands.describe(
        forum_channel="The forum channel to track",
        spreadsheet_id="The Google Spreadsheet ID",
        include_history="Whether to load all historical posts (True) or only track new ones (False)"
    )
    @is_admin_or_owner()
    async def setup_forum_tracker(
        self,
        interaction: discord.Interaction,
        forum_channel: discord.ForumChannel,
        spreadsheet_id: str,
        include_history: bool = True
    ):
        """Setup forum tracking to Google Sheets"""
        try:
            # Check if headers exist
            result = self.sheet_service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range="B1:G1"
            ).execute()

            # Only creates headers if they don't exist
            if 'values' not in result:
                self.sheet_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range="B1:G1",
                    valueInputOption="USER_ENTERED",
                    body={"values": [["Level Name", "Post Description", "Yes Votes", "No Votes", "Ratio", "Date Posted"]]}
                ).execute()

            tracker_data = {
                "forum_id": forum_channel.id,
                "spreadsheet_id": spreadsheet_id,
                "sheet_range": "B2:G",  # Changed to B2:G
                "update_interval": 5,
                "load_history": include_history
            }

            await interaction.response.defer()

            self.bot.settings.set(
                interaction.guild_id,
                "forum_tracker",
                json.dumps(tracker_data),
                SettingType.JSON
            )

            await self.update_forum_data(interaction.guild_id, tracker_data)
            await interaction.followup.send(
                "✅ Forum tracker setup complete!\n" +
                f"• Tracking: {forum_channel.name}\n" +
                "• Sheet Range: B2:G\n" +
                f"• Historical Posts: {'Enabled' if include_history else 'Disabled'}\n" +
                "• Data columns: Level Name, Post Description, Yes Votes, No Votes, Ratio, Date Posted, Status",
                ephemeral=True
            )

        except HttpError as e:
            error_message = f"❌ Error accessing spreadsheet: {str(e)}\nPlease verify the spreadsheet ID and ensure the service account has edit access."
            if not interaction.response.is_done():
                await interaction.response.send_message(error_message, ephemeral=True)
            else:
                await interaction.followup.send(error_message, ephemeral=True)

    @app_commands.command(name="stop_forum_tracker")
    @app_commands.checks.has_permissions(administrator=True)
    async def stop_forum_tracker(self, interaction: discord.Interaction):
        """Stop tracking forum posts"""
        if self.bot.settings.get(interaction.guild_id, "forum_tracker"):
            self.bot.settings.delete(interaction.guild_id, "forum_tracker")
            await interaction.response.send_message("✅ Forum tracker stopped and settings cleared.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ No forum tracker is currently active.", ephemeral=True)

    @app_commands.command(name="view_forum_tracker")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_forum_tracker(self, interaction: discord.Interaction):
        """View current forum tracking settings"""
        tracker_data = self.bot.settings.get(interaction.guild_id, "forum_tracker")
        if not tracker_data:
            await interaction.response.send_message("No forum tracker is currently active.", ephemeral=True)
            return

        tracker_data = json.loads(tracker_data)
        forum_channel = self.bot.get_channel(tracker_data["forum_id"])
        
        embed = discord.Embed(title="Forum Tracker Settings", color=discord.Color.blue())
        embed.add_field(name="Forum Channel", value=forum_channel.mention if forum_channel else "Channel not found", inline=False)
        embed.add_field(name="Spreadsheet ID", value=f"`{tracker_data['spreadsheet_id']}`", inline=False)
        embed.add_field(name="Sheet Range", value=f"`{tracker_data['sheet_range']}`", inline=False)
        embed.add_field(
            name="Update Interval",
            value=f"`{tracker_data.get('update_interval', '5')} minutes`" if tracker_data.get('update_interval') != "on_change" else "`Real-time updates`",
            inline=False
        )
        embed.add_field(name="Historical Posts", value="`Enabled`" if tracker_data.get('load_history', False) else "`Disabled`", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(GoogleSheets(bot))
