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

    async def predicate(ctx_or_interaction):
        settings = Settings.get()

        # Handle both Context and Interaction objects
        if isinstance(ctx_or_interaction, commands.Context):
            author = ctx_or_interaction.author

            async def send_error(msg):
                await ctx_or_interaction.send(msg)
        else:  # Interaction
            author = ctx_or_interaction.user

            async def send_error(msg):
                await ctx_or_interaction.response.send_message(msg, ephemeral=True)

        # Owner check
        if level == PermissionLevel.OWNER:
            if author.id != settings.owner_id:
                await send_error("This command can only be used by the bot owner.")
                return False
            return True

        # Admin check (includes owner)
        if level == PermissionLevel.ADMIN:
            # Check if user is owner (owners are always admins)
            if author.id == settings.owner_id:
                return True

            # Check if user ID is in admin list
            if author.id in settings.admin_user_ids:
                return True

            # Check if user has any admin roles
            user_roles = [role.id for role in author.roles]
            if any(role_id in settings.admin_role_ids for role_id in user_roles):
                return True

            await send_error("This command requires admin privileges.")
            return False

        return False  # Invalid permission level

    def decorator(func):
        if isinstance(func, commands.Command):
            return commands.check(predicate)(func)
        else:

            @wraps(func)
            async def wrapper(self, interaction, *args, **kwargs):
                if await predicate(interaction):
                    return await func(self, interaction, *args, **kwargs)

            return wrapper

    return decorator
