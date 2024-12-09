import discord
from discord.ext import commands, tasks
from datetime import datetime
from typing import Tuple, Optional, Dict, List
from src.utils.decorators import can_use, PermissionLevel
from src.features.spreadsheets.helpers.google import GoogleSheetsClient
from src.core.config import Settings
from src.utils.logger import logger
from src.core.database.models import ManagedServer, ValidTag
from src.core.database.database import get_db
from discord import app_commands

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
        self.google_sheets_client = GoogleSheetsClient(
            credentials_path=str(self.settings.credentials_path),
            token_path="data/token.json",
        )
        self.check_interval_minutes = 10

        # Start background tasks
        self.check_votes.start()
        self.process_backlog.start()

    async def get_server_config(self, guild_id: int) -> Optional[ManagedServer]:
        """Get server configuration from database"""
        with get_db() as db:
            return (
                db.query(ManagedServer)
                .filter(
                    ManagedServer.server_id == str(guild_id),
                    ManagedServer.enabled.is_(True),
                )
                .first()
            )

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

        valid_tags = await self.get_valid_tags(thread.guild.id)
        yes_emoji = valid_tags["yes"][0] if valid_tags["yes"] else "✅"
        no_emoji = valid_tags["no"][0] if valid_tags["no"] else "❌"

        try:
            # Add initial reactions
            first_message = await thread.fetch_message(thread.id)
            await first_message.add_reaction(yes_emoji)
            await first_message.add_reaction(no_emoji)

            # Add initial vote tag
            await self.update_thread_tags(thread, "Initial Vote")

            logger.info(f"Initialized new thread: {thread.name} ({thread.id})")
        except Exception as e:
            logger.error(f"Error initializing thread {thread.id}: {e}")

    @tasks.loop(minutes=10)
    async def check_votes(self):
        """Periodically check votes on active threads"""
        try:
            channel = self.bot.get_channel(self.forum_channel_id)
            if not channel:
                logger.error("Could not find forum channel")
                return

            async for thread in channel.archived_threads(limit=None):
                await self.process_thread_votes(thread)

            # Check active threads
            async for thread in channel.threads():
                await self.process_thread_votes(thread)

        except Exception as e:
            logger.error(f"Error in check_votes: {e}")

    @tasks.loop(hours=24)
    async def process_backlog(self):
        """Process historical threads once per day"""
        try:
            channel = self.bot.get_channel(self.forum_channel_id)
            if not channel:
                return

            async for thread in channel.archived_threads(limit=None):
                await self.process_thread_votes(thread)

        except Exception as e:
            logger.error(f"Error processing backlog: {e}")

    async def process_thread_votes(self, thread: discord.Thread):
        """Process votes for a single thread"""
        try:
            yes_votes, no_votes = await self.count_votes(thread)
            total_votes = yes_votes + no_votes

            if total_votes == 0:
                return

            yes_ratio = yes_votes / total_votes
            current_tags = [tag.name for tag in thread.applied_tags]

            # Determine new tag based on vote ratio
            new_tag = "Added to list" if yes_ratio > 0.5 else "Not added to list"

            # Check if tag has changed
            old_tag = next(
                (
                    tag
                    for tag in ["Added to list", "Not added to list"]
                    if tag in current_tags
                ),
                None,
            )

            if old_tag and old_tag != new_tag:
                # Vote ratio has flipped, notify owners
                await self.notify_owners(
                    f"Vote ratio has flipped for thread '{thread.name}' ({thread.jump_url})\n"
                    f"New ratio: {yes_votes}/{total_votes} votes ({yes_ratio:.2%})\n"
                    f"Status changed from '{old_tag}' to '{new_tag}'"
                )

            # Update tags
            await self.update_thread_tags(thread, new_tag)

            # Update spreadsheet if necessary
            if new_tag == "Added to list":
                await self.add_to_spreadsheet(thread)

        except Exception as e:
            logger.error(f"Error processing thread {thread.id}: {e}")

    async def count_votes(self, thread: discord.Thread) -> Tuple[int, int]:
        """Count yes and no votes in a thread"""
        try:
            first_message = await thread.fetch_message(thread.id)
            yes_votes = 0
            no_votes = 0

            for reaction in first_message.reactions:
                emoji_name = str(reaction.emoji)
                if emoji_name in VALID_YES_EMOJIS:
                    yes_votes += reaction.count - 1  # Subtract bot's reaction
                elif emoji_name in VALID_NO_EMOJIS:
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
                if tag.name
                not in ["Added to list", "Not added to list", "Initial Vote"]
            ]

            # Add new tag
            current_tags.append(available_tags[new_tag])

            # Update thread tags
            await thread.edit(applied_tags=current_tags)

        except Exception as e:
            logger.error(f"Error updating tags for thread {thread.id}: {e}")

    async def add_to_spreadsheet(self, thread: discord.Thread):
        """Add thread information to the spreadsheet"""
        try:
            # Get thread information
            first_message = await thread.fetch_message(thread.id)

            # Prepare row data
            row_data = [
                [
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),  # Timestamp
                    thread.name,  # Thread Title
                    first_message.content,  # Content
                    thread.jump_url,  # Thread URL
                    str(thread.owner),  # Author
                    thread.owner.id,  # Author ID
                ]
            ]

            # Append to spreadsheet
            success = self.google_sheets_client.append_rows(
                spreadsheet_id=self.spreadsheet_id,
                range_name=f"{self.sheet_name}!A:F",
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
        forum_channel="The forum channel", spreadsheet_id="The spreadsheet ID"
    )
    @can_use(PermissionLevel.ADMIN)
    async def add_server(
        self,
        interaction: discord.Interaction,
        forum_channel: discord.TextChannel,
        spreadsheet_id: str,
    ):
        with get_db() as db:
            server = ManagedServer(
                server_id=str(interaction.guild.id),
                forum_channel_id=str(forum_channel.id),
                spreadsheet_id=spreadsheet_id,
            )
            db.add(server)
            db.commit()
        await interaction.response.send_message("✅ Server added successfully!")

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


async def setup(bot: commands.Bot):
    await bot.add_cog(SpreadsheetCog(bot))
