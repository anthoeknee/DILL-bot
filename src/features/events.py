from discord.ext import commands


async def setup(bot):
    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        # Handle message event
