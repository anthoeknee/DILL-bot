import discord
from discord.ext import commands
from discord import app_commands
from src.core.feature_manager import FeatureManager
from src.utils.logger import logger
from src.utils.decorators import can_use, PermissionLevel
from src.core.config import Settings
from typing import List, Dict


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.feature_manager: FeatureManager = bot.feature_manager
        self.settings = Settings.get()

    def get_commands_from_cog(self, cog: commands.Cog) -> List[app_commands.Command]:
        """Get all slash commands from a cog"""
        commands = []

        # Get commands directly from the cog's __cog_app_commands__ attribute
        if hasattr(cog, "__cog_app_commands__"):
            commands.extend(cog.__cog_app_commands__)

        return commands

    @app_commands.command(name="help", description="Show help information")
    @app_commands.describe(feature="Get help for a specific feature")
    async def help_command(self, interaction: discord.Interaction, feature: str = None):
        """Provides an overview of available commands and features."""
        try:
            if feature:
                await self.send_feature_help(interaction, feature)
            else:
                await self.send_general_help(interaction)

        except Exception as e:
            logger.error(f"Error in help command: {e}")
            await interaction.response.send_message(
                "An error occurred while processing the help command.", ephemeral=True
            )

    async def send_general_help(self, interaction: discord.Interaction):
        """Sends a general help message with all available commands."""
        embed = discord.Embed(
            title="Bot Help",
            description="Here's a list of available commands and features:",
            color=discord.Color.blue(),
        )

        # Get all cogs and their commands
        categories: Dict[str, List[app_commands.Command]] = {}

        for cog_name, cog in self.bot.cogs.items():
            # Skip the help cog itself if you want
            # if cog_name == "HelpCog":
            #     continue

            commands = self.get_commands_from_cog(cog)
            if commands:
                # Remove "Cog" suffix from category name
                category_name = cog_name.replace("Cog", "")
                categories[category_name] = commands

        # Add commands to embed by category
        for category, commands in categories.items():
            command_list = []
            for command in commands:
                # Check permissions
                if self.is_owner_command(command) and not await self.is_owner(
                    interaction.user
                ):
                    continue
                if self.is_admin_command(command) and not await self.is_admin(
                    interaction.user
                ):
                    continue

                # Get command description and parameters
                params = []
                for param in command.parameters:
                    if param.required:
                        params.append(f"<{param.name}>")
                    else:
                        params.append(f"[{param.name}]")

                param_str = " " + " ".join(params) if params else ""
                description = command.description or "No description available."

                command_list.append(f"`/{command.name}{param_str}`\n↳ {description}")

            if command_list:
                embed.add_field(
                    name=f"**{category}**",
                    value="\n\n".join(command_list),
                    inline=False,
                )

        # Add footer with additional help info
        embed.set_footer(
            text="Use /help <feature> for more detailed information about specific features"
        )

        await interaction.response.send_message(embed=embed)

    async def send_feature_help(self, interaction: discord.Interaction, feature: str):
        """Sends help information for a specific feature."""
        # Convert feature name to expected cog name format
        cog_name = f"{feature.capitalize()}Cog"
        cog = self.bot.get_cog(cog_name)

        if not cog:
            await interaction.response.send_message(
                f"Feature '{feature}' not found.", ephemeral=True
            )
            return

        commands = self.get_commands_from_cog(cog)
        embed = discord.Embed(
            title=f"{feature.capitalize()} Feature Help",
            description=f"Detailed information about {feature} commands:",
            color=discord.Color.blue(),
        )

        for command in commands:
            # Check permissions
            if self.is_owner_command(command) and not await self.is_owner(
                interaction.user
            ):
                continue
            if self.is_admin_command(command) and not await self.is_admin(
                interaction.user
            ):
                continue

            # Build parameter info
            params = []
            param_descriptions = []
            for param in command.parameters:
                if param.required:
                    params.append(f"<{param.name}>")
                else:
                    params.append(f"[{param.name}]")

                # Add parameter description if available
                if param.description:
                    param_descriptions.append(f"• `{param.name}`: {param.description}")

            param_str = " " + " ".join(params) if params else ""

            # Build command help text
            help_text = command.description or "No description available."

            # Add parameter descriptions if any exist
            if param_descriptions:
                help_text += "\n\n**Parameters:**\n" + "\n".join(param_descriptions)

            # Add detailed help from docstring if available
            if (
                command.callback.__doc__
                and command.callback.__doc__.strip() != command.description
            ):
                doc = command.callback.__doc__.strip()
                help_text += f"\n\n**Details:**\n{doc}"

            embed.add_field(
                name=f"`/{command.name}{param_str}`", value=help_text, inline=False
            )

        await interaction.response.send_message(embed=embed)

    def is_owner_command(self, command: app_commands.Command) -> bool:
        """Checks if a command is owner-only based on decorators."""
        for check in command.checks:
            if hasattr(check, "__qualname__") and check.__qualname__.startswith(
                "can_use.<locals>.predicate"
            ):
                if hasattr(check, "__closure__") and check.__closure__:
                    return check.__closure__[0].cell_contents == PermissionLevel.OWNER
        return False

    def is_admin_command(self, command: app_commands.Command) -> bool:
        """Checks if a command is admin-only based on decorators."""
        for check in command.checks:
            if hasattr(check, "__qualname__") and check.__qualname__.startswith(
                "can_use.<locals>.predicate"
            ):
                if hasattr(check, "__closure__") and check.__closure__:
                    return check.__closure__[0].cell_contents == PermissionLevel.ADMIN
        return False

    async def is_owner(self, user: discord.User) -> bool:
        """Checks if a user is the bot owner."""
        return user.id == self.settings.owner_id

    async def is_admin(self, user: discord.User) -> bool:
        """Checks if a user is an admin."""
        if await self.is_owner(user):
            return True
        if user.id in self.settings.admin_user_ids:
            return True
        # Check for admin roles (if applicable)
        if isinstance(user, discord.Member):
            user_roles = [role.id for role in user.roles]
            if any(role_id in self.settings.admin_role_ids for role_id in user_roles):
                return True
        return False

    @app_commands.command(name="sync", description="Sync slash commands")
    @can_use(PermissionLevel.ADMIN)
    async def sync_commands(
        self, interaction: discord.Interaction, guild_id: str = None
    ):
        """
        Sync slash commands with Discord (Admin only).

        Parameters:
        • guild_id: Optional server ID to sync commands to a specific server
        """
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
