from typing import Dict, List, Optional, Set, Union
from dataclasses import dataclass
from enum import IntEnum
import discord
from datetime import datetime
from .settings_service import SettingsService
from discord.ext import commands
import logging

class PermissionLevel(IntEnum):
    """Defines granular permission levels for commands and users."""
    USER = 0
    HELPER = 10
    MODERATOR = 20
    SENIOR_MODERATOR = 30
    ADMINISTRATOR = 40
    SENIOR_ADMINISTRATOR = 50
    GUILD_OWNER = 60
    BOT_ADMIN = 80
    BOT_OWNER = 100

    @classmethod
    def get_level_name(cls, level: int) -> str:
        """Get friendly name for permission level."""
        try:
            return cls(level).name.replace('_', ' ').title()
        except ValueError:
            return f"Custom Level {level}"

@dataclass
class CommandPermission:
    """Stores permission requirements for a command."""
    command_name: str
    min_level: PermissionLevel
    allowed_roles: Set[int]
    denied_roles: Set[int]
    allowed_users: Set[int]
    denied_users: Set[int]
    guild_id: Optional[int]

class PermissionService:
    """Manages permission levels and command access."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the permission service.
        
        Args:
            bot: Discord bot instance
        """
        self.bot = bot
        self.settings = SettingsService(bot.config)
        self._cache: Dict[int, Dict[str, CommandPermission]] = {}

    async def _load_guild_permissions(self, guild_id: int) -> Dict[str, CommandPermission]:
        """Load guild-specific permissions from settings.
        
        Args:
            guild_id: Discord guild ID

        Returns:
            Dictionary mapping command names to their permissions
        """
        try:
            # Get command permissions
            perms_setting = await self.settings.get_setting(
                key="command_permissions",
                scope="guild",
                scope_id=guild_id
            )
            
            guild_perms = {}
            if perms_setting and perms_setting.value:
                for cmd_name, cmd_data in perms_setting.value.items():
                    guild_perms[cmd_name] = CommandPermission(
                        command_name=cmd_name,
                        min_level=PermissionLevel(cmd_data.get('min_level', 0)),
                        allowed_roles=set(cmd_data.get('allowed_roles', [])),
                        denied_roles=set(cmd_data.get('denied_roles', [])),
                        allowed_users=set(cmd_data.get('allowed_users', [])),
                        denied_users=set(cmd_data.get('denied_users', [])),
                        guild_id=guild_id
                    )

            self._cache[guild_id] = guild_perms
            return guild_perms

        except Exception as e:
            logger.error(f"Error loading permissions: {e}")
            self._cache[guild_id] = {}
            return {}

    async def get_user_level(
        self,
        guild: discord.Guild,
        user: Union[discord.Member, discord.User]
    ) -> PermissionLevel:
        """Calculate the effective permission level for a user.
        
        Args:
            guild: Discord guild
            user: Discord user or member

        Returns:
            User's permission level
        """
        if user.id == self.bot.owner_id:
            return PermissionLevel.BOT_OWNER

        if not isinstance(user, discord.Member):
            return PermissionLevel.EVERYONE

        try:
            role_levels = await self.settings.get_setting(
                key="role_levels",
                scope="guild",
                scope_id=guild.id
            )

            max_level = PermissionLevel.EVERYONE
            
            if role_levels and role_levels.value:
                for role in user.roles:
                    level = role_levels.value.get(str(role.id), 0)
                    max_level = max(max_level, PermissionLevel(level))

            if guild.owner_id == user.id:
                max_level = max(max_level, PermissionLevel.OWNER)

            return max_level

        except Exception as e:
            print(f"Error getting user level: {e}")
            return PermissionLevel.EVERYONE

    async def set_command_permission(
        self,
        guild_id: int,
        command_name: str,
        min_level: PermissionLevel,
        allowed_roles: Optional[Set[int]] = None,
        denied_roles: Optional[Set[int]] = None
    ) -> None:
        """Set permissions for a command in a guild.
        
        Args:
            guild_id: Discord guild ID
            command_name: Name of the command
            min_level: Minimum permission level required
            allowed_roles: Set of allowed role IDs
            denied_roles: Set of denied role IDs
        """
        try:
            perms = await self.settings.get_setting(
                key="command_permissions",
                scope="guild",
                scope_id=guild_id
            )
            
            all_perms = perms.value if perms else {}
            
            all_perms[command_name] = {
                'min_level': min_level,
                'allowed_roles': list(allowed_roles or set()),
                'denied_roles': list(denied_roles or set())
            }

            await self.settings.set_setting(
                key="command_permissions",
                value=all_perms,
                scope="guild",
                scope_id=guild_id,
                category="Permissions",
                description="Command permission settings"
            )

            if guild_id not in self._cache:
                self._cache[guild_id] = {}

            self._cache[guild_id][command_name] = CommandPermission(
                command_name=command_name,
                min_level=min_level,
                allowed_roles=allowed_roles or set(),
                denied_roles=denied_roles or set(),
                guild_id=guild_id
            )

        except Exception as e:
            print(f"Error setting command permission: {e}")
            raise

    async def set_role_level(
        self,
        guild_id: int,
        role_id: int,
        level: PermissionLevel
    ) -> None:
        """Set the permission level for a role.
        
        Args:
            guild_id: Discord guild ID
            role_id: Discord role ID
            level: Permission level to set
        """
        try:
            role_levels = await self.settings.get_setting(
                key="role_levels",
                scope="guild",
                scope_id=guild_id
            )
            
            all_levels = role_levels.value if role_levels else {}
            all_levels[str(role_id)] = level

            await self.settings.set_setting(
                key="role_levels",
                value=all_levels,
                scope="guild",
                scope_id=guild_id,
                category="Permissions",
                description="Role permission levels"
            )

        except Exception as e:
            print(f"Error setting role level: {e}")
            raise

    async def can_run_command(
        self,
        ctx: discord.Interaction,
        command_name: str
    ) -> bool:
        """Check if a user can run a specific command."""
        # Bot owner can always run commands
        if ctx.user.id == self.bot.owner_id:
            return True

        # For DMs, only allow bot owner or deny based on command
        if not ctx.guild:
            return False

        if ctx.guild.id not in self._cache:
            await self._load_guild_permissions(ctx.guild.id)

        cmd_perms = self._cache[ctx.guild.id].get(command_name)
        if not cmd_perms:
            return True  # No restrictions set

        # Check user-specific permissions first
        if ctx.user.id in cmd_perms.denied_users:
            return False
        if ctx.user.id in cmd_perms.allowed_users:
            return True

        # Get user's permission level
        user_level = await self.get_user_level(ctx.guild, ctx.user)
        
        # Check role-specific permissions
        if isinstance(ctx.user, discord.Member):
            user_role_ids = {role.id for role in ctx.user.roles}
            
            if cmd_perms.denied_roles & user_role_ids:
                return False
            if cmd_perms.allowed_roles & user_role_ids:
                return True

        # Finally, check permission level
        return user_level >= cmd_perms.min_level

    async def get_command_permissions(
        self,
        guild_id: int,
        command_name: Optional[str] = None
    ) -> Dict[str, CommandPermission]:
        """Get command permissions for a guild.
        
        Args:
            guild_id: Discord guild ID
            command_name: Optional specific command name

        Returns:
            Dictionary of command permissions
        """
        if guild_id not in self._cache:
            await self._load_guild_permissions(guild_id)

        if command_name:
            return {command_name: self._cache[guild_id].get(command_name)}
        return self._cache[guild_id]

    async def get_role_levels(self, guild_id: int) -> Dict[int, PermissionLevel]:
        """Get permission levels for all roles in a guild.

        Args:
            guild_id: Discord guild ID

        Returns:
            Dictionary mapping role IDs to their permission levels
        """
        try:
            role_levels = await self.settings.get_setting(
                key="role_levels",
                scope="guild",
                scope_id=guild_id
            )
            
            if role_levels and role_levels.value:
                # Convert string keys back to integers and values to PermissionLevel
                return {
                    int(role_id): PermissionLevel(level) 
                    for role_id, level in role_levels.value.items()
                }
            return {}
            
        except Exception as e:
            logger.error(f"Error getting role levels: {e}")
            return {}

async def setup(bot: commands.Bot) -> None:
    """Set up the permissions service module."""
    bot.permissions = PermissionService(bot)
