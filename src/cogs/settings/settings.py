import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Dict, Any
from src.services.settings_service import SettingsService
from src.utils.helpers.sync import CommandSyncManager

class SettingsView(discord.ui.View):
    """Interactive settings menu view"""
    
    def __init__(self, cog: 'SettingsCog', timeout: float = 180):
        """
        Args:
            cog: The settings cog instance
            timeout: View timeout in seconds
        """
        super().__init__(timeout=timeout)
        self.cog = cog
        self.settings = cog.settings
        self.current_page = "main"
        self.current_setting: Optional[str] = None

    async def create_main_menu(self, interaction: discord.Interaction) -> discord.Embed:
        """Create the main settings menu embed
        
        Args:
            interaction: The Discord interaction
        """
        embed = discord.Embed(
            title="⚙️ Bot Settings",
            description="Select an option below to manage bot settings",
            color=discord.Color.blue()
        )
        
        # Determine scope based on channel type
        scope = "guild" if isinstance(interaction.channel, discord.TextChannel) else "user"
        scope_id = interaction.guild_id if scope == "guild" else interaction.user.id
        
        # Get all settings for current scope
        settings = await self.settings.get_all_settings(scope, scope_id)
        
        if settings:
            # Group settings by category if they have one
            categories: Dict[str, List[Any]] = {}
            for setting in settings:
                category = getattr(setting, 'category', 'General')
                if category not in categories:
                    categories[category] = []
                categories[category].append(setting)
            
            for category, cat_settings in categories.items():
                value = "\n".join(f"`{s.key}`: {s.value}" for s in cat_settings)
                embed.add_field(
                    name=f"📁 {category}",
                    value=value or "No settings",
                    inline=False
                )
        else:
            embed.add_field(
                name="No Settings",
                value="No settings have been configured yet",
                inline=False
            )

        # Add warning message if incorrect context
        if scope == "guild" and not isinstance(interaction.channel, discord.TextChannel):
            embed.add_field(
                name="⚠️ Warning",
                value="Guild settings can only be modified in server channels",
                inline=False
            )
        elif scope == "user" and not isinstance(interaction.channel, discord.DMChannel):
            embed.add_field(
                name="⚠️ Warning",
                value="User settings can only be modified in DMs",
                inline=False
            )
        
        embed.set_footer(text=f"Scope: {scope.title()}")
        return embed

    @discord.ui.button(label="Add Setting", style=discord.ButtonStyle.green, emoji="➕")
    async def add_setting(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to add a new setting"""
        # Validate context
        if not self._validate_scope_context(interaction):
            await interaction.response.send_message(
                f"❌ {scope.title()} settings can only be modified in "
                f"{'server channels' if scope == 'guild' else 'DMs'}",
                ephemeral=True
            )
            return
        
        modal = AddSettingModal(self.cog, self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Setting", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_setting(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to edit an existing setting"""
        settings = await self.settings.get_all_settings(self.scope, self.scope_id)
        if not settings:
            await interaction.response.send_message(
                "❌ No settings available to edit",
                ephemeral=True
            )
            return

        # Create select menu with settings
        select = SettingSelect(
            settings,
            placeholder="Choose a setting to edit",
            min_values=1,
            max_values=1
        )
        
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message(
            "Select a setting to edit:",
            view=view,
            ephemeral=True
        )

    @discord.ui.button(label="Delete Setting", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_setting(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Button to delete a setting"""
        settings = await self.settings.get_all_settings(self.scope, self.scope_id)
        if not settings:
            await interaction.response.send_message(
                "❌ No settings available to delete",
                ephemeral=True
            )
            return

        # Create select menu with settings
        select = SettingSelect(
            settings,
            placeholder="Choose a setting to delete",
            min_values=1,
            max_values=1
        )
        
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message(
            "Select a setting to delete:",
            view=view,
            ephemeral=True
        )

    def _validate_scope_context(self, interaction: discord.Interaction) -> bool:
        """Validate if the current scope matches the channel context.
        
        Returns:
            bool: True if the scope is valid for the current context
        """
        if self.scope == "guild":
            return isinstance(interaction.channel, discord.TextChannel)
        else:  # user scope
            return isinstance(interaction.channel, discord.DMChannel)

class AddSettingModal(discord.ui.Modal, title="Add New Setting"):
    """Modal for adding a new setting"""
    
    key = discord.ui.TextInput(
        label="Setting Key",
        placeholder="Enter setting key...",
        min_length=1,
        max_length=100
    )
    
    value = discord.ui.TextInput(
        label="Setting Value",
        placeholder="Enter setting value...",
        min_length=1,
        max_length=1000
    )
    
    description = discord.ui.TextInput(
        label="Description (Optional)",
        placeholder="Enter setting description...",
        required=False,
        max_length=1000
    )
    
    category = discord.ui.TextInput(
        label="Category (Optional)",
        placeholder="Enter category name...",
        required=False,
        max_length=100
    )

    def __init__(self, cog: 'SettingsCog', settings_view: SettingsView):
        super().__init__()
        self.cog = cog
        self.settings_view = settings_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await self.cog.settings.set_setting(
                key=self.key.value,
                value=self.value.value,
                scope=self.settings_view.scope,
                scope_id=self.settings_view.scope_id,
                description=self.description.value,
                category=self.category.value or "General"
            )
            
            embed = await self.settings_view.create_main_menu(interaction)
            await interaction.response.edit_message(
                embed=embed,
                view=self.settings_view
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error adding setting: {str(e)}",
                ephemeral=True
            )

class SettingSelect(discord.ui.Select):
    """Select menu for choosing a setting"""
    
    def __init__(self, settings: List[Any], **kwargs):
        options = [
            discord.SelectOption(
                label=setting.key,
                description=setting.description[:100] if setting.description else None,
                value=setting.key
            )
            for setting in settings
        ]
        super().__init__(options=options, **kwargs)

@app_commands.guild_only()
class SettingsCog(commands.Cog):
    """Cog for managing bot settings through an interactive menu."""
    
    def __init__(self, bot):
        self.bot = bot
        self.settings = SettingsService(bot.config)
        self.sync_manager = CommandSyncManager(bot)

    @app_commands.command(name="settings")
    async def settings_menu(self, interaction: discord.Interaction):
        """Open the interactive settings menu"""
        try:
            # Auto-determine scope based on channel type
            scope = "guild" if isinstance(interaction.channel, discord.TextChannel) else "user"
            
            # Validate channel type matches scope
            if scope == "guild" and not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(
                    "❌ Server settings can only be modified in server channels",
                    ephemeral=True
                )
                return
            elif scope == "user" and not isinstance(interaction.channel, discord.DMChannel):
                await interaction.response.send_message(
                    "❌ User settings can only be modified in DMs",
                    ephemeral=True
                )
                return
            
            view = SettingsView(self)
            embed = await view.create_main_menu(interaction)
            await interaction.response.send_message(
                embed=embed,
                view=view,
                ephemeral=True
            )
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error opening settings menu: {str(e)}",
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(SettingsCog(bot))
