import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, List, Set
from src.services.permission_service import PermissionService, PermissionLevel

class PermissionsCog(commands.Cog):
    """Manages bot permissions and access levels."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.perms: PermissionService = bot.permissions

    @app_commands.command(name="permissions", description="Manage command permissions")
    @app_commands.default_permissions(administrator=True)
    async def permissions(self, interaction: discord.Interaction):
        """Display and manage permission settings."""
        view = PermissionsView(self)
        embed = await view.create_permissions_embed(interaction.guild)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="setrolelevel", description="Set permission level for a role")
    @app_commands.default_permissions(administrator=True)
    async def set_role_level(
        self,
        interaction: discord.Interaction,
        role: discord.Role,
        level: int
    ):
        """Set the permission level for a role."""
        try:
            perm_level = PermissionLevel(level)
            await self.perms.set_role_level(interaction.guild.id, role.id, perm_level)
            await interaction.response.send_message(
                f"✅ Set {role.mention}'s permission level to {perm_level.name}",
                ephemeral=True
            )
        except ValueError:
            await interaction.response.send_message(
                f"❌ Invalid permission level. Valid levels: "
                f"{', '.join(f'{l.name} ({l.value})' for l in PermissionLevel)}",
                ephemeral=True
            )

class PermissionsView(discord.ui.View):
    def __init__(self, cog: PermissionsCog):
        super().__init__(timeout=300)
        self.cog = cog

    async def create_permissions_embed(self, guild: discord.Guild) -> discord.Embed:
        """Create an embed showing current permission settings."""
        embed = discord.Embed(
            title="🔒 Permission Settings",
            description="Manage command permissions and access levels",
            color=discord.Color.blue()
        )

        # Add field showing all permission levels
        level_descriptions = []
        for level in PermissionLevel:
            level_descriptions.append(f"`{level.value}` - {level.name}")
        
        embed.add_field(
            name="Permission Levels",
            value="\n".join(level_descriptions),
            inline=False
        )

        # Get command permissions
        perms = await self.cog.perms._load_guild_permissions(guild.id)
        if perms:
            cmd_perms = []
            for cmd, p in perms.items():
                perm_text = [f"`{cmd}`: {p.min_level.name}"]
                
                if p.allowed_users:
                    users = [f"<@{uid}>" for uid in p.allowed_users]
                    perm_text.append(f"Allowed Users: {', '.join(users)}")
                    
                if p.denied_users:
                    users = [f"<@{uid}>" for uid in p.denied_users]
                    perm_text.append(f"Denied Users: {', '.join(users)}")
                    
                if p.allowed_roles:
                    roles = [f"<@&{rid}>" for rid in p.allowed_roles]
                    perm_text.append(f"Allowed Roles: {', '.join(roles)}")
                
                cmd_perms.append("\n".join(perm_text))
                
            embed.add_field(
                name="Command Permissions",
                value="\n\n".join(cmd_perms) or "No command permissions set",
                inline=False
            )

        # Get role levels
        role_levels = await self.cog.perms.get_role_levels(guild.id)
        if role_levels:
            level_text = []
            for role_id, level in role_levels.items():
                role = guild.get_role(role_id)
                if role:
                    level_text.append(f"{role.mention}: {level.name}")
            
            if level_text:
                embed.add_field(
                    name="Role Levels",
                    value="\n".join(level_text),
                    inline=False
                )

        embed.set_footer(text="Use the buttons below to modify permissions")
        return embed

    @discord.ui.button(label="Set Command Level", style=discord.ButtonStyle.primary)
    async def set_command_level(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to set command permission level."""
        await interaction.response.send_modal(CommandLevelModal(self.cog))

    @discord.ui.button(label="Set Role Level", style=discord.ButtonStyle.secondary)
    async def set_role_level(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to set role permission level."""
        await interaction.response.send_modal(RoleLevelModal(self.cog))

    @discord.ui.button(label="Reset Permissions", style=discord.ButtonStyle.danger)
    async def reset_permissions(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Reset all permission settings."""
        await interaction.response.send_message(
            "Are you sure you want to reset all permissions?",
            view=ConfirmResetView(self.cog),
            ephemeral=True
        )

class CommandLevelModal(discord.ui.Modal, title="Set Command Permission Level"):
    def __init__(self, cog: PermissionsCog):
        super().__init__()
        self.cog = cog

    command = discord.ui.TextInput(
        label="Command Name",
        placeholder="Enter command name..."
    )
    
    level = discord.ui.TextInput(
        label="Permission Level (0-100)",
        placeholder="Enter level number..."
    )
    
    allowed_users = discord.ui.TextInput(
        label="Allowed Users (Optional)",
        placeholder="User IDs separated by commas",
        required=False
    )
    
    denied_users = discord.ui.TextInput(
        label="Denied Users (Optional)",
        placeholder="User IDs separated by commas",
        required=False
    )
    
    allowed_roles = discord.ui.TextInput(
        label="Allowed Roles (Optional)",
        placeholder="Role IDs separated by commas",
        required=False
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Parse level
            level = PermissionLevel(int(self.level.value))
            
            # Parse users and roles
            allowed_users = {int(uid.strip()) for uid in self.allowed_users.value.split(',') if uid.strip()}
            denied_users = {int(uid.strip()) for uid in self.denied_users.value.split(',') if uid.strip()}
            allowed_roles = {int(rid.strip()) for rid in self.allowed_roles.value.split(',') if rid.strip()}
            
            await self.cog.perms.set_command_permission(
                interaction.guild.id,
                self.command.value,
                level,
                allowed_roles=allowed_roles,
                allowed_users=allowed_users,
                denied_users=denied_users
            )
            
            embed = await PermissionsView(self.cog).create_permissions_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed)
            
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Invalid input: {str(e)}",
                ephemeral=True
            )

class RoleLevelModal(discord.ui.Modal, title="Set Role Permission Level"):
    def __init__(self, cog: PermissionsCog):
        super().__init__()
        self.cog = cog

    role_id = discord.ui.TextInput(
        label="Role ID",
        placeholder="Enter role ID..."
    )
    
    level = discord.ui.TextInput(
        label="Permission Level",
        placeholder="Enter level (0-100)..."
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            role_id = int(self.role_id.value)
            level = PermissionLevel(int(self.level.value))
            
            await self.cog.perms.set_role_level(
                interaction.guild.id,
                role_id,
                level
            )
            
            embed = await PermissionsView(self.cog).create_permissions_embed(interaction.guild)
            await interaction.response.edit_message(embed=embed)
            
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Invalid input: {str(e)}",
                ephemeral=True
            )

class ConfirmResetView(discord.ui.View):
    def __init__(self, cog: PermissionsCog):
        super().__init__(timeout=60)
        self.cog = cog

    @discord.ui.button(label="Confirm Reset", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Reset all permissions for the guild."""
        await self.cog.perms.set_command_permission(
            interaction.guild.id,
            "*",  # Special key for all commands
            PermissionLevel.USER,
            allowed_roles=set(),
            denied_roles=set(),
            allowed_users=set(),
            denied_users=set()
        )
        
        embed = await PermissionsView(self.cog).create_permissions_embed(interaction.guild)
        await interaction.response.edit_message(
            content="✅ All permissions have been reset.",
            embed=embed,
            view=None
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Cancel the reset operation."""
        await interaction.response.edit_message(
            content="❌ Reset cancelled.",
            view=None
        )

async def setup(bot: commands.Bot) -> None:
    """Set up the permissions cog."""
    await bot.add_cog(PermissionsCog(bot))
