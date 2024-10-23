from typing import Optional
from discord import Message, Client, DMChannel, Permissions
from discord.ext import commands
import asyncio

class OnMessageHandler(commands.Cog):
    """Handles Discord message events."""

    def __init__(self, bot: commands.Bot):
        """Initialize the message handler.
        
        Args:
            bot: Discord bot instance
        """
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: Message) -> None:
        """Process incoming Discord messages.
        
        Args:
            message: Discord message object
        """
        # Ignore messages from bots (including self)
        if message.author.bot:
            return

        # Process commands
        await self.bot.process_commands(message)

async def setup(bot: commands.Bot) -> None:
    """Setup function for the extension.
    
    Args:
        bot: Discord bot instance
    """
    handler = OnMessageHandler(bot)
    await bot.add_cog(handler)
