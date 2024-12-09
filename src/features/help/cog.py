import discord
from discord.ext import commands
from discord import app_commands
from src.core.feature_manager import FeatureManager
from src.utils.logger import logger
from src.utils.decorators import can_use, PermissionLevel


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.feature_manager: FeatureManager = bot.feature_manager

    @app_commands.command(name="help", description="Show help information")
    async def help_command(self, interaction: discord.Interaction):
        """Provides an overview of available commands and features."""
        try:
            embed = discord.Embed(
                title="Bot Help",
                description="Here's a list of available commands and features:",
                color=discord.Color.blue(),
            )

            # Get loaded features
            features = self.feature_manager.loaded_features

            # Add Spreadsheets section first
            spreadsheet_cog = self.bot.get_cog("SpreadsheetCog")
            if spreadsheet_cog:
                spreadsheet_commands = [
                    "`/add_server` - Add a server to the bot's management",
                    "`/remove_server` - Remove server from bot's management",
                    "`/add_tag` - Add a valid tag",
                    "`/remove_tag` - Remove a valid tag",
                    "`/list_tags` - List all valid tags for this server",
                ]
                embed.add_field(
                    name="**Spreadsheets**",
                    value="\n".join(spreadsheet_commands),
                    inline=False,
                )

            # Add other features
            for feature_name in features:
                if (
                    feature_name.lower() != "spreadsheets"
                ):  # Skip spreadsheets as we already added it
                    cog = self.bot.get_cog(f"{feature_name.capitalize()}Cog")
                    if cog:
                        cog_commands = cog.get_app_commands()
                        if cog_commands:
                            embed.add_field(
                                name=f"**{feature_name.capitalize()}**",
                                value=", ".join(
                                    [
                                        f"`/{command.name}`"
                                        for command in cog_commands
                                        if isinstance(command, app_commands.Command)
                                    ]
                                ),
                                inline=False,
                            )

            await interaction.response.send_message(embed=embed)

        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await interaction.response.send_message(
                "An error occurred while processing the help command."
            )

    @app_commands.command(name="sync", description="Sync slash commands")
    @can_use(PermissionLevel.ADMIN)
    async def sync_commands(
        self, interaction: discord.Interaction, guild_id: str = None
    ):
        """Sync slash commands (admin only)."""
        try:
            if guild_id:
                try:
                    guild_id = int(guild_id)
                except ValueError:
                    await interaction.response.send_message(
                        "Invalid guild ID format.", ephemeral=True
                    )
                    return
            else:
                guild_id = None

            await self.feature_manager.sync_commands(guild_id)
            await interaction.response.send_message("Commands synced successfully.")

        except Exception as e:
            logger.error(f"Error in sync_commands: {e}")
            await interaction.response.send_message(
                "An error occurred while syncing commands."
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
