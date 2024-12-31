from typing import Mapping, Optional, List
from discord.ext import commands
import discord
import logging


class HelpCommand(commands.Cog, name="Help"):
    def __init__(self, prefix: str):
        super().__init__()
        self.prefix = prefix

    def get_command_signature(self, command: commands.Command):
        """Returns a formatted command signature."""
        return f"{self.prefix}{command.name} {command.signature}"

    async def send_bot_help(
        self, mapping: Mapping[Optional[commands.Cog], List[commands.Command]]
    ):
        """Sends help for all commands."""
        embed = discord.Embed(title="Bot Commands", color=discord.Color.blue())

        for cog, cmds in mapping.items():
            filtered = await self.filter_commands(cmds, sort=True)
            if filtered:
                name = getattr(cog, "qualified_name", "No Category")
                command_signatures = [
                    f"`{self.get_command_signature(c)}`" for c in filtered
                ]
                if command_signatures:
                    embed.add_field(
                        name=name, value="\n".join(command_signatures), inline=False
                    )

        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_command_help(self, command: commands.Command):
        """Sends help for a specific command."""
        embed = discord.Embed(title=f"Help: {command.name}", color=discord.Color.blue())
        embed.add_field(
            name="Usage", value=f"`{self.get_command_signature(command)}`", inline=False
        )
        if command.help:
            embed.add_field(name="Description", value=command.help, inline=False)
        if command.aliases:
            embed.add_field(
                name="Aliases",
                value=", ".join(f"`{alias}`" for alias in command.aliases),
                inline=False,
            )
        channel = self.get_destination()
        await channel.send(embed=embed)

    async def send_group_help(self, group: commands.Group):
        """Sends help for a command group."""
        await self.send_bot_help({None: group.commands})

    async def send_cog_help(self, cog: commands.Cog):
        """Sends help for a cog."""
        await self.send_bot_help({cog: cog.get_commands()})

    async def send_error_message(self, error: str):
        """Sends an error message."""
        embed = discord.Embed(
            title="Error", description=error, color=discord.Color.red()
        )
        channel = self.get_destination()
        await channel.send(embed=embed)

    async def command_not_found(self, string: str):
        """Sends a message when a command is not found."""
        return f"No command called '{string}' found."

    async def subcommand_not_found(self, command: commands.Command, string: str):
        """Sends a message when a subcommand is not found."""
        return f"No subcommand called '{string}' found for command '{command.name}'."

    async def send_help_embed(
        self,
        ctx: commands.Context,
        entity: commands.Command | commands.Cog | commands.Group | None = None,
    ):
        """Sends the appropriate help message based on the entity."""
        if entity is None:
            mapping = {cog: cog.get_commands() for cog in ctx.bot.cogs.values()}
            await self.send_bot_help(mapping)
        elif isinstance(entity, commands.Command):
            await self.send_command_help(entity)
        elif isinstance(entity, commands.Group):
            await self.send_group_help(entity)
        elif isinstance(entity, commands.Cog):
            await self.send_cog_help(entity)

    @commands.command(name="help")
    async def help(self, ctx: commands.Context, *, command_name: str = None):
        """Shows this message"""
        if command_name:
            entity = ctx.bot.get_cog(command_name) or ctx.bot.get_command(command_name)
            if entity:
                await self.send_help_embed(ctx, entity)
            else:
                await ctx.send(await self.command_not_found(command_name))
        else:
            await self.send_help_embed(ctx)


async def setup(bot: commands.Bot):
    """
    Sets up the Help cog and adds it to the bot.

    This function is called by the bot when loading extensions.
    """
    prefix = bot.config_manager.get_config().get("bot", {}).get("prefix", "!")
    cog = HelpCommand(prefix)
    await bot.add_cog(cog)
    logging.info("Help cog loaded")
