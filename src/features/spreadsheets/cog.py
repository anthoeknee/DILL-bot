import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional, Dict, List
from src.utils.decorators import can_use, PermissionLevel
from src.features.spreadsheets.helpers.google import GoogleSheetsClient
from src.core.config import Settings
from src.utils.logger import logger
from src.core.database.models import ManagedServer, ValidTag
from src.core.database.database import get_db
from discord import app_commands
import asyncio

VALID_YES_EMOJIS = [
    "pickle_yes",
    "white_check_mark",
    "abobaheavenlymerveilleuxinstantw",
]
VALID_NO_EMOJIS = ["pickle_no", "x"]
NEW_YES_EMOJI = "pickle_yes"
NEW_NO_EMOJI = "pickle_no"

TAG_IDS = {
    "NOT_IN_LIST": 1258877875457626154,
    "ADDED_TO_LIST": 1298038416025452585,
    "INITIAL_VOTE": 1315553680874803291,
}


class SpreadsheetCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = Settings.get()

        # Initialize with empty credentials if file doesn't exist yet
        try:
            self.google_sheets_client = GoogleSheetsClient(
                credentials_path=str(self.settings.credentials_path)
            )
        except Exception as e:
            logger.warning(f"Failed to initialize Google Sheets client: {e}")
            self.google_sheets_client = None

        self.check_interval_minutes = 10

        # Start background tasks
        self.check_votes.start()
        self.process_backlog.start()
        self.check_ratios.start()  # Start the ratio checking task

    async def get_server_config(self, guild_id: int) -> Optional[ManagedServer]:
        """Get server configuration from database"""
        with get_db() as db:
            server_config = (
                db.query(ManagedServer)
                .filter(
                    ManagedServer.server_id == str(guild_id),
                    ManagedServer.enabled.is_(True),
                )
                .first()
            )
        logger.debug(f"Retrieved server config for guild {guild_id}: {server_config}")
        return server_config

    async def get_valid_tags(self, guild_id: int) -> Dict[str, List[str]]:
        """Get valid tags for a server"""
        with get_db() as db:
            tags = db.query(ValidTag).filter(ValidTag.server_id == str(guild_id)).all()

        return {
            "yes": [tag.name for tag in tags if tag.tag_type == "yes"],
            "no": [tag.name for tag in tags if tag.tag_type == "no"],
            "status": [tag.name for tag in tags if tag.tag_type == "status"],
        }

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        """Handle new thread creation in the forum channel"""
        server_config = await self.get_server_config(thread.guild.id)
        if not server_config or thread.parent_id != int(server_config.forum_channel_id):
            return

        try:
            # Get valid tags but fall back to unicode emojis if none configured
            valid_tags = await self.get_valid_tags(thread.guild.id)

            # For yes emoji: Try custom emoji first, fall back to ✅
            yes_emoji = None
            if valid_tags["yes"]:
                yes_emoji_name = valid_tags["yes"][0]
                yes_emoji = discord.utils.get(thread.guild.emojis, name=yes_emoji_name)
            yes_emoji = yes_emoji or "✅"

            # For no emoji: Try custom emoji first, fall back to ❌
            no_emoji = None
            if valid_tags["no"]:
                no_emoji_name = valid_tags["no"][0]
                no_emoji = discord.utils.get(thread.guild.emojis, name=no_emoji_name)
            no_emoji = no_emoji or "❌"

            # Add initial reactions
            first_message = await thread.fetch_message(thread.id)
            await first_message.add_reaction(yes_emoji)
            await first_message.add_reaction(no_emoji)

            # Get available tags
            forum_channel = thread.parent
            available_tags = {tag.name: tag for tag in forum_channel.available_tags}

            # Add initial vote tag
            if "Initial Vote" in available_tags:
                await thread.edit(applied_tags=[available_tags["Initial Vote"]])
                logger.info(
                    f"Added Initial Vote tag to thread: {thread.name} ({thread.id})"
                )
            else:
                logger.error(f"Initial Vote tag not found for thread {thread.id}")

        except Exception as e:
            logger.error(f"Error initializing thread {thread.id}: {e}")

    @tasks.loop(minutes=10)
    async def check_votes(self):
        """Periodically check votes on active threads"""
        try:
            # Process each configured server
            with get_db() as db:
                servers = (
                    db.query(ManagedServer)
                    .filter(ManagedServer.enabled.is_(True))
                    .all()
                )

            for server in servers:
                channel = self.bot.get_channel(int(server.forum_channel_id))
                if not channel:
                    logger.error(
                        f"Could not find forum channel for server {server.server_id}"
                    )
                    continue

                # Process threads that are at least 24 hours old
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)

                # Process archived threads
                async for thread in channel.archived_threads(limit=None):
                    if thread.created_at <= cutoff_time:
                        await self.process_thread_votes(thread)

                # Process active threads
                async for thread in channel.threads():
                    if thread.created_at <= cutoff_time:
                        await self.process_thread_votes(thread)

        except Exception as e:
            logger.error(f"Error in check_votes: {e}")

    @tasks.loop(hours=24)
    async def process_backlog(self):
        """Process historical threads once per day"""
        try:
            # Process each configured server
            with get_db() as db:
                servers = (
                    db.query(ManagedServer)
                    .filter(ManagedServer.enabled.is_(True))
                    .all()
                )

            for server in servers:
                channel = self.bot.get_channel(int(server.forum_channel_id))
                if not channel:
                    continue

                async for thread in channel.archived_threads(limit=None):
                    await self.process_thread_votes(thread)

        except Exception as e:
            logger.error(f"Error processing backlog: {e}")

    async def process_thread_votes(self, thread: discord.Thread):
        """Process votes for a single thread"""
        try:
            # Check if thread is at least 24 hours old
            time_since_creation = datetime.now(timezone.utc) - thread.created_at
            if time_since_creation < timedelta(hours=24):
                return

            # Check current tags by ID
            current_tag_ids = [str(tag.id) for tag in thread.applied_tags]

            # Skip if thread already has a final status tag
            if (
                str(TAG_IDS["ADDED_TO_LIST"]) in current_tag_ids
                or str(TAG_IDS["NOT_IN_LIST"]) in current_tag_ids
            ):
                return

            # Only process if "Initial Vote" tag is present
            if str(TAG_IDS["INITIAL_VOTE"]) not in current_tag_ids:
                return

            yes_votes, no_votes = await self.count_votes(thread)
            total_votes = yes_votes + no_votes

            if total_votes == 0:
                return

            yes_ratio = yes_votes / total_votes

            # Determine if approved based on ratio
            is_approved = yes_ratio > 0.5001

            # Update tags
            await self.update_thread_tags(thread, is_approved)

            # Update spreadsheet if necessary
            if is_approved:
                await self.add_to_spreadsheet(thread)

            # Notify about the tag change
            status = "Added to List" if is_approved else "Not in Any List"
            await self.notify_owners(
                f"Thread '{thread.name}' ({thread.jump_url}) has been processed:\n"
                f"Final ratio: {yes_votes}/{total_votes} votes ({yes_ratio:.2%})\n"
                f"Status: {status}"
            )

        except discord.HTTPException as e:
            logger.error(f"Error processing votes for thread {thread.id}: {e}")
            # Add error handling logic here, e.g., retry, notify user, etc.
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while processing votes for thread {thread.id}: {e}"
            )
            # Handle other potential errors

    async def count_votes(self, thread: discord.Thread) -> Tuple[int, int]:
        """Count yes and no votes in a thread"""
        try:
            first_message = await thread.fetch_message(thread.id)
            logger.debug(f"Counting votes for thread {thread.id}")
            logger.debug(
                f"Reactions: {[str(r.emoji) for r in first_message.reactions]}"
            )
            yes_votes = 0
            no_votes = 0

            for reaction in first_message.reactions:
                # Get the actual emoji name or unicode character
                if isinstance(reaction.emoji, str):
                    emoji_name = reaction.emoji
                else:
                    emoji_name = reaction.emoji.name.lower()

                # Check both custom emoji names and unicode emojis
                if emoji_name in VALID_YES_EMOJIS or emoji_name == "✅":
                    yes_votes += reaction.count - 1  # Subtract bot's reaction
                elif emoji_name in VALID_NO_EMOJIS or emoji_name == "❌":
                    no_votes += reaction.count - 1  # Subtract bot's reaction

            return yes_votes, no_votes

        except discord.HTTPException as e:
            logger.error(f"Error counting votes for thread {thread.id}: {e}")
            # Add error handling logic here
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while counting votes for thread {thread.id}: {e}"
            )
            # Handle other potential errors

    async def update_thread_tags(self, thread: discord.Thread, is_approved: bool):
        """Update thread tags using tag IDs"""
        try:
            # Get available tags
            forum_channel = thread.parent
            available_tags = {str(tag.id): tag for tag in forum_channel.available_tags}

            # Determine new tag ID based on approval
            new_tag_id = str(
                TAG_IDS["ADDED_TO_LIST"] if is_approved else TAG_IDS["NOT_IN_LIST"]
            )

            if new_tag_id not in available_tags:
                logger.error(f"Tag ID {new_tag_id} not found in available tags")
                return

            # Remove old status tags
            current_tags = [
                tag
                for tag in thread.applied_tags
                if str(tag.id)
                not in [
                    str(TAG_IDS["ADDED_TO_LIST"]),
                    str(TAG_IDS["NOT_IN_LIST"]),
                    str(TAG_IDS["INITIAL_VOTE"]),
                ]
            ]

            # Add new tag
            current_tags.append(available_tags[new_tag_id])

            # Update thread tags
            await thread.edit(applied_tags=current_tags)
            logger.info(f"Updated tags for thread {thread.id}")

        except discord.HTTPException as e:
            logger.error(f"Error updating tags for thread {thread.id}: {e}")
            # Add error handling logic here
        except Exception as e:
            logger.error(
                f"An unexpected error occurred while updating tags for thread {thread.id}: {e}"
            )
            # Handle other potential errors

    async def add_to_spreadsheet(self, thread: discord.Thread):
        """Add thread information to the spreadsheet"""
        try:
            # Get server config to get spreadsheet ID
            server_config = await self.get_server_config(thread.guild.id)
            if not server_config:
                logger.error(f"No server config found for thread {thread.id}")
                return

            # Get thread information
            first_message = await thread.fetch_message(thread.id)
            yes_votes, no_votes = await self.count_votes(thread)
            total_votes = yes_votes + no_votes
            vote_ratio = yes_votes / total_votes if total_votes > 0 else 0

            # Prepare row data (starting from column B)
            row_data = [
                [
                    thread.name,  # Level Name (B)
                    first_message.content,  # Post Description (C)
                    str(yes_votes),  # Yes Votes (D)
                    str(no_votes),  # No Votes (E)
                    f"{vote_ratio:.2%}",  # Ratio (F)
                    thread.created_at.strftime("%Y-%m-%d"),  # Date Posted (G)
                ]
            ]

            # Append to spreadsheet starting at B2
            success = self.google_sheets_client.append_rows(
                spreadsheet_id=server_config.spreadsheet_id,
                range_name="B2:G2",  # Specify range starting at B2
                values=row_data,
            )

            if success:
                logger.info(f"Added thread {thread.id} to spreadsheet")
            else:
                logger.error(f"Failed to add thread {thread.id} to spreadsheet")

        except Exception as e:
            logger.error(f"Error adding thread {thread.id} to spreadsheet: {e}")

    async def notify_owners(self, message: str):
        """Notify bot owners about important changes"""
        try:
            # Get owner user object
            owner = await self.bot.fetch_user(self.settings.owner_id)
            if owner:
                await owner.send(message)

            # Notify additional admins
            for admin_id in self.settings.admin_user_ids:
                try:
                    admin = await self.bot.fetch_user(admin_id)
                    if admin:
                        await admin.send(message)
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")

        except discord.HTTPException as e:
            logger.error(f"Error notifying owners: {e}")
            # Add error handling logic here
        except Exception as e:
            logger.error(f"An unexpected error occurred in notify_owners: {e}")
            # Handle other potential errors

    @commands.command()
    @can_use(PermissionLevel.OWNER)
    async def force_check(self, ctx: commands.Context):
        """Force check all threads (owner only)"""
        await ctx.send("Starting forced check of all threads...")
        await self.check_votes()
        await ctx.send("Forced check completed!")

    @commands.command()
    @can_use(PermissionLevel.OWNER)
    async def process_history(self, ctx: commands.Context):
        """Process all historical threads (owner only)"""
        await ctx.send("Starting historical thread processing...")
        await self.process_backlog()
        await ctx.send("Historical processing completed!")

    @app_commands.command(
        name="add_server", description="Add a server to the bot's management"
    )
    @app_commands.describe(
        forum_channel="The forum channel",
        spreadsheet_id="The Google Sheets spreadsheet ID",
    )
    @can_use(PermissionLevel.ADMIN)
    async def add_server(
        self,
        interaction: discord.Interaction,
        forum_channel: discord.ForumChannel,
        spreadsheet_id: str,
    ):
        """Add a server to the bot's management with spreadsheet validation"""
        await interaction.response.defer(thinking=True)

        # Validate spreadsheet ID
        if not self.google_sheets_client:
            await interaction.followup.send(
                "❌ Google Sheets integration is not properly configured."
            )
            return

        try:
            # Validate spreadsheet ID first
            is_valid = await self.google_sheets_client.validate_spreadsheet_id(
                spreadsheet_id
            )
            if not is_valid:
                await interaction.followup.send(
                    "❌ Invalid spreadsheet ID. Please make sure:\n"
                    "1. The spreadsheet ID is correct\n"
                    "2. The bot's service account has access to the spreadsheet"
                )
                return

            with get_db() as db:
                # Check if server already exists
                existing = (
                    db.query(ManagedServer)
                    .filter(
                        ManagedServer.server_id == str(interaction.guild_id)
                    )  # Changed from guild.id
                    .first()
                )

                if existing:
                    existing.forum_channel_id = str(forum_channel.id)
                    existing.spreadsheet_id = spreadsheet_id
                    existing.enabled = True
                    db.commit()
                    await interaction.followup.send(
                        "✅ Server configuration updated successfully!"
                    )
                    return

                # Create new server entry
                server = ManagedServer(
                    server_id=str(interaction.guild_id),  # Changed from guild.id
                    forum_channel_id=str(forum_channel.id),
                    spreadsheet_id=spreadsheet_id,
                    enabled=True,
                )
                db.add(server)
                db.commit()

                logger.info(
                    f"Added new server: {server.server_id} with channel {server.forum_channel_id}"
                )
                await interaction.followup.send("✅ Server added successfully!")

        except Exception as e:
            logger.error(f"Error adding server: {e}", exc_info=True)
            await interaction.followup.send(
                "❌ An error occurred while adding the server. Please check the logs."
            )

    @app_commands.command(
        name="remove_server", description="Remove this server from the bot's management"
    )
    @can_use(PermissionLevel.ADMIN)
    async def remove_server(self, interaction: discord.Interaction):
        with get_db() as db:
            db.query(ManagedServer).filter(
                ManagedServer.server_id == str(interaction.guild.id)
            ).delete()
            db.commit()
        await interaction.response.send_message("✅ Server removed successfully!")

    @app_commands.command(name="add_tag", description="Add a valid tag")
    @app_commands.describe(name="The tag name", tag_type="The tag type")
    @app_commands.choices(
        tag_type=[
            app_commands.Choice(name="yes", value="yes"),
            app_commands.Choice(name="no", value="no"),
            app_commands.Choice(name="status", value="status"),
        ]
    )
    @can_use(PermissionLevel.ADMIN)
    async def add_tag(self, interaction: discord.Interaction, name: str, tag_type: str):
        if tag_type not in ["yes", "no", "status"]:
            await interaction.response.send_message(
                "❌ Tag type must be 'yes', 'no', or 'status'"
            )
            return

        with get_db() as db:
            tag = ValidTag(
                server_id=str(interaction.guild.id), name=name, tag_type=tag_type
            )
            db.add(tag)
            db.commit()
        await interaction.response.send_message(
            f"✅ Tag '{name}' added as {tag_type} tag!"
        )

    @app_commands.command(name="remove_tag", description="Remove a valid tag")
    @app_commands.describe(name="The tag name")
    @can_use(PermissionLevel.ADMIN)
    async def remove_tag(self, interaction: discord.Interaction, name: str):
        with get_db() as db:
            db.query(ValidTag).filter(
                ValidTag.server_id == str(interaction.guild.id), ValidTag.name == name
            ).delete()
            db.commit()
        await interaction.response.send_message(f"✅ Tag '{name}' removed!")

    @app_commands.command(
        name="list_tags", description="List all valid tags for this server"
    )
    @can_use(PermissionLevel.ADMIN)
    async def list_tags(self, interaction: discord.Interaction):
        with get_db() as db:
            tags = (
                db.query(ValidTag)
                .filter(ValidTag.server_id == str(interaction.guild.id))
                .all()
            )

        if not tags:
            await interaction.response.send_message(
                "No tags configured for this server."
            )
            return

        embed = discord.Embed(title="Valid Tags", color=discord.Color.blue())

        for tag_type in ["yes", "no", "status"]:
            type_tags = [tag.name for tag in tags if tag.tag_type == tag_type]
            if type_tags:
                embed.add_field(
                    name=f"{tag_type.title()} Tags",
                    value="\n".join(type_tags),
                    inline=False,
                )

        await interaction.response.send_message(embed=embed)

    async def process_thread_data(self, thread: discord.Thread):
        """Process a single thread and return its data"""
        try:
            yes_votes, no_votes = await self.count_votes(thread)
            total_votes = yes_votes + no_votes
            vote_ratio = yes_votes / total_votes if total_votes > 0 else 0

            first_message = await thread.fetch_message(thread.id)

            return {
                "name": thread.name,
                "content": first_message.content,
                "yes_votes": str(yes_votes),
                "no_votes": str(no_votes),
                "ratio": f"{vote_ratio:.2%}",
                "created_at": thread.created_at,
                "row_data": [
                    thread.name,
                    first_message.content,
                    str(yes_votes),
                    str(no_votes),
                    f"{vote_ratio:.2%}",
                    thread.created_at.strftime("%Y-%m-%d"),
                ],
            }
        except Exception as e:
            logger.error(f"Error processing thread {thread.id}: {e}")
            return None

    @app_commands.command(
        name="sync_spreadsheet", description="Sync all forum threads to the spreadsheet"
    )
    @can_use(PermissionLevel.ADMIN)
    async def sync_spreadsheet(self, interaction: discord.Interaction):
        """Manually sync all forum threads to the spreadsheet (admin only)"""
        await interaction.response.defer(thinking=True)

        try:
            server_config = await self.get_server_config(interaction.guild.id)
            if not server_config:
                await interaction.followup.send(
                    "This server is not configured for spreadsheet management."
                )
                return

            channel = self.bot.get_channel(int(server_config.forum_channel_id))
            if not channel or not isinstance(channel, discord.ForumChannel):
                await interaction.followup.send(
                    "Could not find the configured forum channel."
                )
                return

            # Collect all threads in a single list
            progress_msg = await interaction.followup.send("Collecting threads...")
            all_threads = []
            all_threads.extend([t for t in channel.threads])

            # Fetch archived threads in larger batches
            async for thread in channel.archived_threads(limit=None):
                all_threads.append(thread)

            await progress_msg.edit(content=f"Processing {len(all_threads)} threads...")

            # Process threads in larger batches with concurrent execution
            BATCH_SIZE = 50
            all_data = []

            for i in range(0, len(all_threads), BATCH_SIZE):
                batch = all_threads[i : i + BATCH_SIZE]

                # Process each batch concurrently
                tasks = []
                for thread in batch:
                    # Fetch first message and reactions concurrently
                    tasks.append(
                        asyncio.gather(
                            thread.fetch_message(thread.id), self.count_votes(thread)
                        )
                    )

                # Wait for all tasks in batch to complete
                batch_results = await asyncio.gather(*tasks)

                # Process results
                for thread, (message, (yes_votes, no_votes)) in zip(
                    batch, batch_results
                ):
                    total_votes = yes_votes + no_votes
                    vote_ratio = yes_votes / total_votes if total_votes > 0 else 0

                    all_data.append(
                        {
                            "created_at": thread.created_at,
                            "row_data": [
                                thread.name,
                                message.content,
                                str(yes_votes),
                                str(no_votes),
                                f"{vote_ratio:.2%}",
                                thread.created_at.strftime("%Y-%m-%d"),
                            ],
                        }
                    )

                await progress_msg.edit(
                    content=f"Processed {min(i + BATCH_SIZE, len(all_threads))}/{len(all_threads)} threads..."
                )

            # Sort by creation date
            all_data.sort(key=lambda x: x["created_at"], reverse=True)
            batch_data = [data["row_data"] for data in all_data]

            await progress_msg.edit(content="Updating spreadsheet...")

            # Batch update spreadsheet in a single API call
            if batch_data:
                success = self.google_sheets_client.batch_update_values(
                    spreadsheet_id=server_config.spreadsheet_id, data=batch_data
                )

                if success:
                    # Set column widths after updating data
                    self.google_sheets_client.set_column_widths(
                        spreadsheet_id=server_config.spreadsheet_id
                    )

                    await progress_msg.edit(
                        content=f"✅ Successfully synced {len(batch_data)} threads to the spreadsheet!"
                    )
                else:
                    await progress_msg.edit(
                        content="❌ Failed to write data to the spreadsheet."
                    )
            else:
                await progress_msg.edit(content="No threads found to sync.")

        except Exception as e:
            logger.error(f"Error in sync_spreadsheet: {e}")
            await interaction.followup.send(
                "❌ An error occurred while syncing the spreadsheet."
            )

    @app_commands.command(
        name="process_untagged",
        description="Process all untagged threads and add appropriate tags based on vote ratios",
    )
    @can_use(PermissionLevel.ADMIN)
    async def process_untagged(self, interaction: discord.Interaction):
        """Process all threads without status tags and add appropriate tags based on vote ratios"""
        await interaction.response.defer(thinking=True)

        try:
            server_config = await self.get_server_config(interaction.guild.id)
            if not server_config:
                await interaction.followup.send(
                    "This server is not configured for management."
                )
                return

            channel = self.bot.get_channel(int(server_config.forum_channel_id))
            if not channel or not isinstance(channel, discord.ForumChannel):
                await interaction.followup.send(
                    "Could not find the configured forum channel."
                )
                return

            progress_msg = await interaction.followup.send("Collecting threads...")

            # Collect all threads
            all_threads = []
            all_threads.extend([t for t in channel.threads])
            async for thread in channel.archived_threads(limit=None):
                all_threads.append(thread)

            # Filter eligible threads
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
            eligible_threads = []

            for thread in all_threads:
                current_tag_ids = [str(tag.id) for tag in thread.applied_tags]
                if (
                    thread.created_at <= cutoff_time
                    and str(TAG_IDS["INITIAL_VOTE"]) in current_tag_ids
                    and str(TAG_IDS["ADDED_TO_LIST"]) not in current_tag_ids
                    and str(TAG_IDS["NOT_IN_LIST"]) not in current_tag_ids
                ):
                    eligible_threads.append(thread)

            if not eligible_threads:
                await progress_msg.edit(content="No eligible threads found to process.")
                return

            await progress_msg.edit(
                content=f"Processing {len(eligible_threads)} threads..."
            )

            # Process threads in smaller batches with rate limiting
            BATCH_SIZE = 5  # Reduced batch size
            processed_count = 0
            approved_threads = []

            for i in range(0, len(eligible_threads), BATCH_SIZE):
                batch = eligible_threads[i : i + BATCH_SIZE]

                # Process batch with rate limiting
                for thread in batch:
                    # Count votes
                    yes_votes, no_votes = await self.count_votes(thread)
                    total_votes = yes_votes + no_votes

                    if total_votes > 0:
                        yes_ratio = yes_votes / total_votes
                        is_approved = yes_ratio > 0.5001

                        # Update tags
                        await self.update_thread_tags(thread, is_approved)
                        processed_count += 1

                        if is_approved:
                            approved_threads.append(thread)

                        # Send notification
                        status = "Added to List" if is_approved else "Not in Any List"
                        await self.notify_owners(
                            f"Thread '{thread.name}' processed: {yes_votes}/{total_votes} votes ({yes_ratio:.2%}) - {status}"
                        )

                    # Add delay between thread processing
                    await asyncio.sleep(1.5)  # 1.5 second delay between threads

                # Update progress every batch
                await progress_msg.edit(
                    content=f"Processed {processed_count}/{len(eligible_threads)} threads..."
                )

                # Add delay between batches
                await asyncio.sleep(2)  # 2 second delay between batches

            # Update spreadsheet for approved threads in smaller batches
            if approved_threads:
                await progress_msg.edit(
                    content="Updating spreadsheet with approved threads..."
                )
                SPREADSHEET_BATCH_SIZE = 5
                for i in range(0, len(approved_threads), SPREADSHEET_BATCH_SIZE):
                    batch = approved_threads[i : i + SPREADSHEET_BATCH_SIZE]
                    for thread in batch:
                        await self.add_to_spreadsheet(thread)
                        await asyncio.sleep(
                            1
                        )  # 1 second delay between spreadsheet updates

            final_message = (
                f"✅ Processed {processed_count} threads!\n"
                f"Added {len(approved_threads)} threads to the spreadsheet."
            )
            await progress_msg.edit(content=final_message)

        except Exception as e:
            logger.error(f"Error in process_untagged: {e}")
            await interaction.followup.send(
                "❌ An error occurred while processing threads."
            )

    @tasks.loop(minutes=10)
    async def check_ratios(self):
        """Periodically check vote ratios and update tags accordingly"""
        try:
            with get_db() as db:
                servers = (
                    db.query(ManagedServer)
                    .filter(ManagedServer.enabled.is_(True))
                    .all()
                )

            for server in servers:
                # Skip if notification channel or tag IDs aren't configured
                if not (
                    server.notification_channel_id
                    and server.added_to_list_tag_id
                    and server.not_in_list_tag_id
                ):
                    logger.debug(
                        f"Skipping server {server.server_id} - missing configuration"
                    )
                    continue

                channel = self.bot.get_channel(int(server.forum_channel_id))
                notification_channel = self.bot.get_channel(
                    int(server.notification_channel_id)
                )

                if not channel or not notification_channel:
                    logger.error(
                        f"Could not find channels for server {server.server_id}"
                    )
                    continue

                # Process both active and archived threads
                threads = []
                try:
                    # Get active threads
                    threads.extend([t for t in channel.threads])

                    # Get archived threads
                    async for thread in channel.archived_threads(limit=None):
                        threads.append(thread)

                    logger.info(
                        f"Processing {len(threads)} threads for server {server.server_id}"
                    )

                    # Process threads in smaller batches to avoid rate limits
                    BATCH_SIZE = 10
                    for i in range(0, len(threads), BATCH_SIZE):
                        batch = threads[i : i + BATCH_SIZE]
                        for thread in batch:
                            try:
                                await self.check_thread_ratio(
                                    thread, server, notification_channel
                                )
                            except Exception as thread_error:
                                logger.error(
                                    f"Error processing thread {thread.id}: {thread_error}"
                                )
                        # Add small delay between batches to avoid rate limits
                        await asyncio.sleep(2)

                except discord.HTTPException as e:
                    logger.error(
                        f"Discord API error while processing server {server.server_id}: {e}"
                    )
                except Exception as e:
                    logger.error(
                        f"Error processing threads for server {server.server_id}: {e}"
                    )

        except Exception as e:
            logger.error(f"Error in check_ratios: {e}")

    @check_ratios.before_loop
    async def before_check_ratios(self):
        """Wait until the bot is ready before starting the task"""
        await self.bot.wait_until_ready()

    async def check_thread_ratio(
        self,
        thread: discord.Thread,
        server: ManagedServer,
        notification_channel: discord.TextChannel,
    ):
        """Check a thread's vote ratio and update tags if necessary"""
        try:
            current_tag_ids = [str(tag.id) for tag in thread.applied_tags]
            yes_votes, no_votes = await self.count_votes(thread)
            total_votes = yes_votes + no_votes

            if total_votes == 0:
                return

            ratio = yes_votes / total_votes

            # Check if thread needs tag updates based on ratio
            if str(server.added_to_list_tag_id) in current_tag_ids and ratio < 0.34:
                # Remove "Added to List" tag and add "Not in List" tag
                await self.update_thread_tags(thread, False)
                await notification_channel.send(
                    f"⚠️ **Alert:** Thread '{thread.name}' has fallen below 34% approval ({ratio:.2%})\n{thread.jump_url}"
                )

            elif str(server.not_in_list_tag_id) in current_tag_ids and ratio > 0.5001:
                # Remove "Not in List" tag and add "Added to List" tag
                await self.update_thread_tags(thread, True)
                await notification_channel.send(
                    f"🎉 **Alert:** Thread '{thread.name}' has risen above 50% approval ({ratio:.2%})\n{thread.jump_url}"
                )

        except Exception as e:
            logger.error(f"Error checking thread ratio: {e}")

    @app_commands.command(
        name="set_notification_channel",
        description="Set the channel for ratio change notifications",
    )
    @can_use(PermissionLevel.ADMIN)
    async def set_notification_channel(
        self, interaction: discord.Interaction, channel: discord.TextChannel
    ):
        """Set the channel where ratio change notifications will be sent"""
        try:
            with get_db() as db:
                server = (
                    db.query(ManagedServer)
                    .filter(ManagedServer.server_id == str(interaction.guild_id))
                    .first()
                )

                if not server:
                    await interaction.response.send_message(
                        "Server not configured yet!"
                    )
                    return

                server.notification_channel_id = str(channel.id)
                db.commit()

            await interaction.response.send_message(
                f"Notification channel set to {channel.mention}"
            )

        except Exception as e:
            logger.error(f"Error setting notification channel: {e}")
            await interaction.response.send_message(
                "An error occurred while setting the notification channel."
            )

    @app_commands.command(
        name="set_tag_ids", description="Set the tag IDs for vote status"
    )
    @can_use(PermissionLevel.ADMIN)
    async def set_tag_ids(
        self,
        interaction: discord.Interaction,
        initial_vote_tag_id: str,
        added_to_list_tag_id: str,
        not_in_list_tag_id: str,
    ):
        """Set the tag IDs used for vote status"""
        try:
            with get_db() as db:
                server = (
                    db.query(ManagedServer)
                    .filter(ManagedServer.server_id == str(interaction.guild_id))
                    .first()
                )

                if not server:
                    await interaction.response.send_message(
                        "Server not configured yet!"
                    )
                    return

                server.initial_vote_tag_id = initial_vote_tag_id
                server.added_to_list_tag_id = added_to_list_tag_id
                server.not_in_list_tag_id = not_in_list_tag_id
                db.commit()

            await interaction.response.send_message("Tag IDs updated successfully!")

        except Exception as e:
            logger.error(f"Error setting tag IDs: {e}")
            await interaction.response.send_message(
                "An error occurred while setting the tag IDs."
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(SpreadsheetCog(bot))
