import discord
from typing import List, Optional, Dict
import logging


class DiscordForumClient(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.reactions = True
        intents.guilds = True
        super().__init__(intents=intents)

        self.logger = logging.getLogger(__name__)

    async def on_ready(self):
        self.logger.info(f"Logged in as {self.user}")

    async def add_reaction(self, message_id: int, channel_id: int, emoji: str) -> bool:
        """Add a reaction to a specific message"""
        try:
            channel = await self.fetch_channel(channel_id)
            message = await channel.fetch_message(message_id)
            await message.add_reaction(emoji)
            return True
        except Exception as e:
            self.logger.error(f"Error adding reaction: {e}")
            return False

    async def get_reactions(
        self, message_id: int, channel_id: int
    ) -> Dict[str, List[discord.User]]:
        """Get all reactions and users who reacted to a specific message"""
        try:
            channel = await self.fetch_channel(channel_id)
            message = await channel.fetch_message(message_id)
            reactions = {}
            for reaction in message.reactions:
                users = await reaction.users().flatten()
                reactions[str(reaction.emoji)] = users
            return reactions
        except Exception as e:
            self.logger.error(f"Error fetching reactions: {e}")
            return {}

    async def create_thread_with_tags(
        self,
        channel_id: int,
        name: str,
        content: str = None,
        tags: List[str] = None,
        auto_archive_duration: int = 1440,
    ) -> Optional[discord.Thread]:
        """Create a new thread with tags in a forum channel"""
        try:
            channel = await self.fetch_channel(channel_id)
            if not isinstance(channel, discord.ForumChannel):
                raise ValueError(f"Channel {channel_id} is not a forum channel")

            available_tags = {tag.name: tag for tag in channel.available_tags}
            selected_tags = [
                available_tags[tag] for tag in tags if tag in available_tags
            ]

            thread = await channel.create_thread(
                name=name,
                content=content,
                auto_archive_duration=auto_archive_duration,
                applied_tags=selected_tags,
            )
            return thread
        except Exception as e:
            self.logger.error(f"Error creating thread with tags: {e}")
            return None

    async def get_thread_tags(self, thread_id: int) -> List[str]:
        """Get tags applied to a specific thread"""
        try:
            thread = await self.fetch_channel(thread_id)
            if not isinstance(thread, discord.Thread):
                raise ValueError(f"Channel {thread_id} is not a thread")

            return [tag.name for tag in thread.applied_tags]
        except Exception as e:
            self.logger.error(f"Error fetching thread tags: {e}")
            return []
