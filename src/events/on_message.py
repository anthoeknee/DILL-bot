import discord
from discord.ext import commands
import json
from typing import Optional
import asyncio
from src.utils.logger import logger

async def setup(bot: commands.Bot) -> None:
    """Sets up the on_message event"""
    
    @bot.event
    async def on_message(message: discord.Message) -> None:
        """Event triggered when a message is sent"""
        # Ignore messages from bots
        if message.author.bot:
            return

        # Process commands first
        await bot.process_commands(message)
        
        # Check if message is in a thread
        if not isinstance(message.channel, discord.Thread):
            return
            
        # Get the parent channel
        parent_channel = message.channel.parent
        if not isinstance(parent_channel, discord.ForumChannel):
            return
            
        # Check if this forum is being tracked
        forum_data: Optional[str] = bot.settings.get(message.guild.id, "forum_tracker")
        if not forum_data:
            return
            
        # Parse forum data
        tracked_forum = json.loads(forum_data)
        
        # Check if this is the tracked forum
        if parent_channel.id != tracked_forum["forum_id"]:
            return
            
        # Only add reactions to the first message in the thread
        async for first_message in message.channel.history(limit=1, oldest_first=True):
            if message.id == first_message.id:
                try:
                    # Define all reactions to add
                    reactions = [
                        "<:pickle_yes:1263941895625900085>",    # Yes vote
                        "<:pickle_no:1263941842244730972>"      # No vote
                    ]
                    
                    # Add each reaction with error handling
                    for reaction in reactions:
                        try:
                            await message.add_reaction(reaction)
                            # Add a small delay between reactions to prevent rate limiting
                            await asyncio.sleep(0.5)
                        except discord.HTTPException as e:
                            logger.error(f"Failed to add reaction {reaction} to message {message.id}: {e}")
                            continue
                        
                except Exception as e:
                    logger.error(f"Error adding reactions to message {message.id}: {e}")
