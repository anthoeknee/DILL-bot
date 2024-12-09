from functools import wraps
from discord.ext import commands
from src.core.config import Settings
from enum import Enum


class PermissionLevel(Enum):
    """Permission levels for command access"""

    OWNER = "owner"
    ADMIN = "admin"


def can_use(level: PermissionLevel):
    """
    Check if the user has the required permission level.
    Usage: @can_use(PermissionLevel.OWNER) or @can_use(PermissionLevel.ADMIN)
    """

    async def predicate(ctx):
        settings = Settings.get()

        # Owner check
        if level == PermissionLevel.OWNER:
            if ctx.author.id != settings.owner_id:
                await ctx.send("This command can only be used by the bot owner.")
                return False
            return True

        # Admin check (includes owner)
        if level == PermissionLevel.ADMIN:
            # Check if user is owner (owners are always admins)
            if ctx.author.id == settings.owner_id:
                return True

            # Check if user ID is in admin list
            if ctx.author.id in settings.admin_user_ids:
                return True

            # Check if user has any admin roles
            user_roles = [role.id for role in ctx.author.roles]
            if any(role_id in settings.admin_role_ids for role_id in user_roles):
                return True

            await ctx.send("This command requires admin privileges.")
            return False

        return False  # Invalid permission level

    return commands.check(predicate)
