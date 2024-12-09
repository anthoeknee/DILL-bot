from discord.ext import commands


async def setup(bot):
    @bot.command()
    async def ping(ctx):
        await ctx.send("Pong!")
