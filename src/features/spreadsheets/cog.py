import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
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
                cutoff_time = datetime.utcnow() - timedelta(hours=24)

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
            time_since_creation = datetime.utcnow() - thread.created_at
            if time_since_creation < timedelta(hours=24):
                return

            yes_votes, no_votes = await self.count_votes(thread)
            total_votes = yes_votes + no_votes

            if total_votes == 0:
                return

            yes_ratio = yes_votes / total_votes
            current_tags = [tag.name for tag in thread.applied_tags]

            # Only process if "Initial Vote" tag is present
            if "Initial Vote" not in current_tags:
                return

            # Determine new tag based on vote ratio (using 50.01% threshold)
            new_tag = "Added to List" if yes_ratio > 0.5001 else "Not in Any List"

            # Update tags
            await self.update_thread_tags(thread, new_tag)

            # Update spreadsheet if necessary
            if new_tag == "Added to List":
                await self.add_to_spreadsheet(thread)

            # Notify about the tag change
            await self.notify_owners(
                f"Thread '{thread.name}' ({thread.jump_url}) has been processed after 24 hours:\n"
                f"Final ratio: {yes_votes}/{total_votes} votes ({yes_ratio:.2%})\n"
                f"Status: {new_tag}"
            )

        except Exception as e:
            logger.error(f"Error processing thread {thread.id}: {e}")

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

        except Exception as e:
            logger.error(f"Error counting votes in thread {thread.id}: {e}")
            return 0, 0

    async def update_thread_tags(self, thread: discord.Thread, new_tag: str):
        """Update thread tags"""
        try:
            # Get available tags
            forum_channel = thread.parent
            available_tags = {tag.name: tag for tag in forum_channel.available_tags}

            if new_tag not in available_tags:
                logger.error(f"Tag '{new_tag}' not found in available tags")
                return

            # Remove old status tags
            current_tags = [
                tag
                for tag in thread.applied_tags
                if tag.name not in ["Added to List", "Not in Any List", "Initial Vote"]
            ]

            # Add new tag
            current_tags.append(available_tags[new_tag])

            # Update thread tags
            await thread.edit(applied_tags=current_tags)
            logger.info(f"Updated tags for thread {thread.id}: {new_tag}")

        except Exception as e:
            logger.error(f"Error updating tags for thread {thread.id}: {e}")

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

        except Exception as e:
            logger.error(f"Error in notify_owners: {e}")

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


async def setup(bot: commands.Bot):
    await bot.add_cog(SpreadsheetCog(bot))
