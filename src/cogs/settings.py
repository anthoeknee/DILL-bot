import discord
from discord import app_commands
from discord.ext import commands
from typing import Any, Optional, Union, Literal, cast
from src.utils.settings_manager import SettingsManager, SettingType
from src.utils.checks import is_owner

SettingTypeLiteral = Literal["string", "integer", "boolean", "json", "float"]

class Settings(commands.GroupCog, group_name="settings"):
    """Manage bot settings"""
    
    def __init__(self, bot: commands.Bot) -> None:
        self.bot: commands.Bot = bot
        # Remove the SettingsManager initialization here
        # self.settings = SettingsManager()  # Remove this line
        super().__init__()

    @app_commands.command(name="view")
    @app_commands.checks.has_permissions(administrator=True)
    async def view_settings(self, interaction: discord.Interaction) -> None:  # This is correct
        """View all settings for this server"""
        settings: dict[str, Any] = self.bot.settings.get_all(interaction.guild_id)
        
        if not settings:
            await interaction.response.send_message(
                "No settings configured for this server.",
                ephemeral=True
            )
            return

        embed: discord.Embed = discord.Embed(
            title="Server Settings",
            color=discord.Color.blue()
        )
        
        for key, value in settings.items():
            embed.add_field(name=key, value=str(value), inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="set")
    @app_commands.describe(
        key="The setting key to update",
        value="The new value for the setting"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @is_owner()
    async def set_setting(
        self,
        interaction: discord.Interaction,
        key: str,
        value: str
    ) -> None:
        """Set a setting value"""
        try:
            setting_type = self._detect_type(value)
            parsed_value = self._parse_value(value, setting_type)
            
            self.bot.settings.set(interaction.guild_id, key, parsed_value, setting_type)
            
            type_names = {
                SettingType.STRING: "text",
                SettingType.INTEGER: "number",
                SettingType.FLOAT: "decimal number",
                SettingType.BOOLEAN: "true/false",
                SettingType.JSON: "JSON"
            }
            
            await interaction.response.send_message(
                f"✅ Setting `{key}` has been updated to `{parsed_value}` (detected as {type_names[setting_type]})",
                ephemeral=True
            )
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Error: {str(e)}",
                ephemeral=True
            )

    @app_commands.command(name="get")
    @app_commands.describe(key="The setting key to retrieve")
    @app_commands.checks.has_permissions(administrator=True)
    async def get_setting(
        self,
        interaction: discord.Interaction,
        key: str
    ) -> None:
        """Get a setting value"""
        value: Optional[Any] = self.bot.settings.get(interaction.guild_id, key)
        if value is None:
            await interaction.response.send_message(
                f"Setting `{key}` is not configured.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"`{key}` = `{value}`",
                ephemeral=True
            )

    @app_commands.command(name="delete")
    @app_commands.describe(key="The setting key to delete")
    @app_commands.checks.has_permissions(administrator=True)
    async def delete_setting(
        self,
        interaction: discord.Interaction,
        key: str
    ) -> None:
        """Delete a setting"""
        self.bot.settings.delete(interaction.guild_id, key)
        await interaction.response.send_message(
            f"Setting `{key}` has been deleted.",
            ephemeral=True
        )

    def _detect_type(self, value: str) -> SettingType:
        """Automatically detect the setting type from the value"""
        value = value.lower().strip()
        
        # Check for boolean
        if value in ('true', 'false', 'yes', 'no', 'on', 'off', '1', '0'):
            return SettingType.BOOLEAN
            
        # Check for integer
        try:
            int(value)
            return SettingType.INTEGER
        except ValueError:
            pass
            
        # Check for float
        try:
            float(value)
            return SettingType.FLOAT
        except ValueError:
            pass
            
        # Check for JSON
        if (value.startswith('{') and value.endswith('}')) or \
           (value.startswith('[') and value.endswith(']')):
            try:
                import json
                json.loads(value)
                return SettingType.JSON
            except json.JSONDecodeError:
                pass
                
        # Default to string
        return SettingType.STRING

    def _parse_value(self, value: str, setting_type: SettingType) -> Any:
        """Parse the string value into the detected type"""
        value = value.lower().strip()
        
        if setting_type == SettingType.BOOLEAN:
            return value in ('true', 'yes', 'on', '1')
        elif setting_type == SettingType.INTEGER:
            return int(value)
        elif setting_type == SettingType.FLOAT:
            return float(value)
        elif setting_type == SettingType.JSON:
            import json
            return json.loads(value)
        else:
            return value

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))
